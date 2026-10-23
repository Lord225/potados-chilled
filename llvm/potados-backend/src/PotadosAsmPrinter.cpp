#include "Potados.h"
#include "PotadosTargetMachine.h"
#include "llvm/ADT/DenseMap.h"
#include "llvm/CodeGen/AsmPrinter.h"
#include "llvm/CodeGen/MachineFunction.h"
#include "llvm/IR/Constants.h"
#include "llvm/IR/DataLayout.h"
#include "llvm/IR/GlobalAlias.h"
#include "llvm/IR/Module.h"
#include "llvm/IR/Operator.h"
#include "llvm/MC/MCContext.h"
#include "llvm/MC/MCStreamer.h"
#include "llvm/MC/MCSymbol.h"
#include "llvm/MC/TargetRegistry.h"
#include "llvm/Support/CommandLine.h"
#include "llvm/Support/ErrorHandling.h"
#include "llvm/Target/TargetLoweringObjectFile.h"
#include <algorithm>
using namespace llvm;
#define DEBUG_TYPE "potados-asm-printer"
static cl::opt<unsigned> InitialSP(
    "potados-initial-sp", cl::init(0x7f00),
    cl::desc("Initial native word address of the architectural stack"));
static cl::opt<std::string> Entry("potados-entry", cl::init("main"),
                                  cl::desc("Startup entry function"));
static cl::opt<bool>
    NoStartup("potados-no-startup", cl::init(false),
              cl::desc("Emit a library assembly module without reset startup"));
namespace {
class PotadosAsmPrinter final : public AsmPrinter {
  DenseMap<const GlobalValue *, uint64_t> Addresses;
  DenseMap<uint64_t, std::string> SymbolBytes;
  uint64_t LocalLabel = 0;
  static std::string name(StringRef N) {
    std::string R;
    for (unsigned char C : N) {
      if (isAlnum(C) || C == '_')
        R += C;
      else {
        R += "_x";
        R += hexdigit(C >> 4);
        R += hexdigit(C & 15);
      }
    }
    return R;
  }
  std::string block(const MachineBasicBlock *B) const {
    return "__potados_bb_" + name(B->getParent()->getName()) + "_" +
           std::to_string(B->getNumber());
  }
  void text(const Twine &S) { OutStreamer->emitRawText(S.str()); }
  void inst(const Twine &S) { text("\t" + S); }
  std::string reg(const MachineOperand &O) const {
    return MF->getSubtarget()
        .getRegisterInfo()
        ->getRegAsmName(O.getReg())
        .str();
  }
  std::string operand(const MachineOperand &O) const {
    if (O.isReg())
      return reg(O);
    if (O.isImm())
      return std::to_string(O.getImm());
    if (O.isMBB())
      return block(O.getMBB());
    if (O.isGlobal())
      return name(O.getGlobal()->getName()) +
             (O.getOffset() ? "+" + std::to_string(O.getOffset()) : "");
    if (O.isSymbol())
      return name(O.getSymbolName());
    report_fatal_error("unsupported POTADOS assembly operand");
  }
  void mov(StringRef D, StringRef S) {
    if (D != S)
      inst("MOV " + D + ", " + S);
  }
  void shift(StringRef D, int64_t Amount, bool Arithmetic = false) {
    if (Amount < -16 || Amount > 15)
      report_fatal_error("invalid POTADOS immediate shift");
    inst(Twine(Arithmetic ? "ASH " : "SH ") + D + ", ZERO, " + Twine(Amount));
  }
  void adjustSP(int64_t Bytes) {
    if (Bytes & 1)
      report_fatal_error("POTADOS stack adjustment must be even");
    Bytes /= 2;
    if (!Bytes)
      return;
    if (Bytes >= -128 && Bytes <= 127)
      inst("ADDI SP, " + Twine(Bytes));
    else {
      inst("LI R6, " + Twine(Bytes));
      inst("ADD SP, SP, R6");
    }
  }
  void stackAccess(bool Load, StringRef V, int64_t Bytes) {
    if (Bytes & 1)
      report_fatal_error("unaligned POTADOS word stack slot");
    Bytes /= 2;
    if (Bytes >= -128 && Bytes <= 127)
      inst(Twine(Load ? "LDSP " : "STSP ") + V + ", " + Twine(Bytes));
    else {
      inst("LI R6, " + Twine(Bytes));
      inst("ADD R6, SP, R6");
      inst(Twine(Load ? "LD " : "ST ") + V + ", [R6]");
    }
  }
  void saveLink() {
    inst("ADDI SP, -1");
    inst("STSP R7, 0");
  }
  void restoreLink() {
    inst("LDSP R7, 0");
    inst("ADDI SP, 1");
  }
  std::string label(StringRef Purpose) {
    return "__potados_" + Purpose.str() + "_" + name(MF->getName()) + "_" +
           std::to_string(LocalLabel++);
  }
  // Canonicalize all ten integer predicates to the six hardware predicates.
  std::string compare(unsigned CC, std::string &A, std::string &B,
                      bool Branch) {
    switch (CC) {
    case ISD::SETGT:
      std::swap(A, B);
      CC = ISD::SETLT;
      break;
    case ISD::SETLE:
      std::swap(A, B);
      CC = ISD::SETGE;
      break;
    case ISD::SETUGT:
      std::swap(A, B);
      CC = ISD::SETULT;
      break;
    case ISD::SETULE:
      std::swap(A, B);
      CC = ISD::SETUGE;
      break;
    }
    StringRef S;
    switch (CC) {
    case ISD::SETEQ:
      S = "E";
      break;
    case ISD::SETNE:
      S = "NE";
      break;
    case ISD::SETLT:
      S = "L";
      break;
    case ISD::SETGE:
      S = "GE";
      break;
    case ISD::SETULT:
      S = "B";
      break;
    case ISD::SETUGE:
      S = "AE";
      break;
    default:
      report_fatal_error("unsupported POTADOS integer predicate");
    }
    return (Branch ? "J" : "S") + S.str();
  }
  std::optional<std::string> addressExpression(const Constant *C) const {
    if (const auto *I = dyn_cast<ConstantInt>(C))
      return std::to_string(I->getSExtValue());
    if (const auto *G = dyn_cast<GlobalValue>(C)) {
      auto I = Addresses.find(G);
      return I == Addresses.end() ? name(G->getName())
                                  : std::to_string(I->second);
    }
    if (const auto *E = dyn_cast<ConstantExpr>(C)) {
      if (E->isCast())
        return addressExpression(cast<Constant>(E->getOperand(0)));
      if (E->getOpcode() == Instruction::Add ||
          E->getOpcode() == Instruction::Sub) {
        auto A = addressExpression(cast<Constant>(E->getOperand(0)));
        auto B = addressExpression(cast<Constant>(E->getOperand(1)));
        if (A && B)
          return "(" + *A + (E->getOpcode() == Instruction::Add ? "+" : "-") +
                 *B + ")";
      }
    }
    return std::nullopt;
  }
  bool encode(const Constant *C, const DataLayout &DL,
              MutableArrayRef<uint8_t> Bytes, uint64_t ByteOffset = 0) {
    if (isa<ConstantAggregateZero, ConstantPointerNull, UndefValue,
            PoisonValue>(C))
      return true;
    if (auto *CI = dyn_cast<ConstantInt>(C)) {
      APInt Bits = CI->getValue().zextOrTrunc(Bytes.size() * 8);
      for (unsigned I = 0; I < Bytes.size(); ++I)
        Bytes[I] = Bits.extractBitsAsZExtValue(8, I * 8);
      return true;
    }
    if (auto *GV = dyn_cast<GlobalValue>(C)) {
      if (!Addresses.count(GV)) {
        if (Bytes.size() != 2)
          return false;
        SymbolBytes[ByteOffset] = "%lo(" + name(GV->getName()) + ")";
        SymbolBytes[ByteOffset + 1] = "%hi(" + name(GV->getName()) + ")";
        return true;
      }
      uint64_t V = Addresses[GV];
      for (unsigned I = 0; I < Bytes.size(); ++I)
        Bytes[I] = V >> (I * 8);
      return true;
    }
    if (auto *CE = dyn_cast<ConstantExpr>(C)) {
      if (CE->getOpcode() == Instruction::Add ||
          CE->getOpcode() == Instruction::Sub) {
        auto E = addressExpression(CE);
        if (!E || Bytes.size() != 2)
          return false;
        SymbolBytes[ByteOffset] = "%lo(" + *E + ")";
        SymbolBytes[ByteOffset + 1] = "%hi(" + *E + ")";
        return true;
      }
      if (CE->isCast())
        return encode(cast<Constant>(CE->getOperand(0)), DL, Bytes, ByteOffset);
      if (auto *GEP = dyn_cast<GEPOperator>(CE)) {
        APInt Offset(16, 0);
        if (!GEP->accumulateConstantOffset(DL, Offset) ||
            !encode(cast<Constant>(GEP->getPointerOperand()), DL, Bytes,
                    ByteOffset))
          return false;
        if (Offset.getZExtValue() & 1)
          return false;
        uint16_t V = uint16_t(Bytes[0] | uint16_t(Bytes[1]) << 8) +
                     Offset.getZExtValue() / 2;
        Bytes[0] = V;
        Bytes[1] = V >> 8;
        return true;
      }
      return false;
    }
    if (auto *CS = dyn_cast<ConstantStruct>(C)) {
      const StructLayout *S = DL.getStructLayout(CS->getType());
      for (unsigned I = 0; I < CS->getNumOperands(); ++I) {
        auto *E = cast<Constant>(CS->getOperand(I));
        if (!encode(E, DL,
                    Bytes.slice(S->getElementOffset(I),
                                DL.getTypeAllocSize(E->getType())),
                    ByteOffset + S->getElementOffset(I)))
          return false;
      }
      return true;
    }
    if (auto *AT = dyn_cast<ArrayType>(C->getType())) {
      uint64_t Stride = DL.getTypeAllocSize(AT->getElementType());
      for (unsigned I = 0; I < AT->getNumElements(); ++I) {
        Constant *E = C->getAggregateElement(I);
        if (!E || !encode(E, DL, Bytes.slice(I * Stride, Stride),
                          ByteOffset + I * Stride))
          return false;
      }
      return true;
    }
    return false;
  }

public:
  static char ID;
  PotadosAsmPrinter(TargetMachine &TM, std::unique_ptr<MCStreamer> S)
      : AsmPrinter(TM, std::move(S), ID) {}
  StringRef getPassName() const override {
    return "POTADOS flat assembly printer";
  }
  void emitStartOfAsmFile(Module &M) override {
    const auto *WordABI = mdconst::dyn_extract_or_null<ConstantInt>(
        M.getModuleFlag("potados.word-addressed"));
    if (!WordABI || !WordABI->equalsInt(1))
      report_fatal_error(
          "POTADOS requires native word ABI IR from its C frontend "
          "(module flag potados.word-addressed = 1)");
    uint64_t Address = 0x100;
    for (auto &F : M) {
      if (!F.isDeclaration()) {
        F.addFnAttr(Attribute::NoUnwind);
        F.removeFnAttr(Attribute::UWTable);
      }
    }
    for (auto &G : M.globals()) {
      if (!G.hasInitializer() || G.getName().starts_with("llvm."))
        continue;
      if (G.isThreadLocal())
        report_fatal_error("POTADOS does not support TLS");
      uint64_t Size = M.getDataLayout().getTypeAllocSize(G.getValueType());
      if (Size & 1)
        report_fatal_error(
            "POTADOS global storage must contain complete 16-bit cells");
      uint64_t Alignment =
          std::max<uint64_t>(1, G.getAlign().valueOrOne().value() / 2);
      Address = alignTo(Address, Alignment);
      Addresses[&G] = Address;
      Address += Size / 2;
      if (Address >= 0x7000)
        report_fatal_error("POTADOS globals exceed the reserved data range");
      text(".equ " + name(G.getName()) + ", " + Twine(Addresses[&G]));
    }
    if (!NoStartup && M.getFunction(Entry) &&
        !M.getFunction(Entry)->isDeclaration()) {
      if (InitialSP > 0x7fff)
        report_fatal_error("POTADOS initial SP must be a RAM word address");
      text(".org 0");
      text("_start:");
      inst("LI SP, " + Twine(InitialSP));
      inst("JAL R7, __potados_init");
      inst("JAL R7, " + name(Entry));
      inst("HALT");
    }
  }
  void emitFunctionHeader() override {
    // The generic function-body emitter uses MF's section again at the end.
    // Establish its bookkeeping without emitting ELF section directives into
    // the project's flat assembly language.
    MF->setSection(
        getObjFileLowering().SectionForGlobal(&MF->getFunction(), TM));
    OutStreamer->switchSectionNoPrint(MF->getSection());
    CurrentFnSym = OutContext.getOrCreateSymbol(name(MF->getName()));
    OutStreamer->emitLabel(CurrentFnSym);
  }
  void emitBasicBlockStart(const MachineBasicBlock &B) override {
    text(block(&B) + ":");
  }
  void emitGlobalVariable(const GlobalVariable *) override {}
  void emitGlobalAlias(const Module &, const GlobalAlias &G) override {
    if (auto *V = G.getAliaseeObject())
      text(".equ " + name(G.getName()) + ", " + name(V->getName()));
    else
      report_fatal_error("unsupported POTADOS alias");
  }
  void emitEndOfAsmFile(Module &M) override {
    text("__potados_init:");
    for (auto &G : M.globals()) {
      if (!Addresses.count(&G))
        continue;
      auto Size =
          M.getDataLayout().getTypeAllocSize(G.getValueType()).getFixedValue();
      SmallVector<uint8_t, 64> Bytes(alignTo(Size, 2), 0);
      SymbolBytes.clear();
      if (!encode(G.getInitializer(), M.getDataLayout(),
                  MutableArrayRef<uint8_t>(Bytes).take_front(Size)))
        report_fatal_error(Twine("unsupported POTADOS global initializer: ") +
                           G.getName());
      for (uint64_t I = 0; I < Bytes.size(); I += 2) {
        unsigned V = Bytes[I] | unsigned(Bytes[I + 1]) << 8;
        if (SymbolBytes.count(I) || SymbolBytes.count(I + 1)) {
          inst("LLI R5, " + (SymbolBytes.count(I) ? SymbolBytes[I]
                                                  : std::to_string(Bytes[I])));
          inst("LUI R6, " + (SymbolBytes.count(I + 1)
                                 ? SymbolBytes[I + 1]
                                 : std::to_string(Bytes[I + 1])));
          inst("OR R5, R5, R6");
        } else
          inst("LI R5, " + Twine(V));
        inst("LI R6, " + Twine(Addresses[&G] + I / 2));
        inst("ST R5, [R6]");
      }
    }
    inst("JMPR R7");
  }
  bool PrintAsmOperand(const MachineInstr *MI, unsigned OpNo, const char *Extra,
                       raw_ostream &OS) override {
    if (!Extra || !*Extra) {
      OS << operand(MI->getOperand(OpNo));
      return false;
    }
    return true;
  }
  void emitInstruction(const MachineInstr *MI) override {
    unsigned Op = MI->getOpcode();
    if (MI->isMetaInstruction())
      return;
    auto O = [&](unsigned N) { return operand(MI->getOperand(N)); };
    switch (Op) {
    case Potados::ADD:
    case Potados::SUB:
    case Potados::AND:
    case Potados::OR:
    case Potados::XOR:
      inst(MF->getSubtarget().getInstrInfo()->getName(Op) + " " + O(0) + ", " +
           O(1) + ", " + O(2));
      return;
    case Potados::MOV:
      mov(O(0), O(1));
      return;
    case Potados::LI:
    case Potados::LIga:
      inst("LI " + O(0) + ", " + O(1));
      return;
    case Potados::MUL8:
      inst("MUL " + O(0) + ", " + O(1) + ", " + O(2));
      return;
    case Potados::MUL16:
      saveLink();
      mov("R6", O(1));
      shift("R6", 8);
      mov("R7", O(2));
      shift("R7", 8);
      inst("MUL R6, R6, " + O(2));
      inst("MUL R7, " + O(1) + ", R7");
      inst("ADD R6, R6, R7");
      shift("R6", -8);
      inst("MUL " + O(0) + ", " + O(1) + ", " + O(2));
      inst("ADD " + O(0) + ", " + O(0) + ", R6");
      restoreLink();
      return;
    case Potados::SHLi:
    case Potados::SRLi:
    case Potados::SRAi:
      mov(O(0), O(1));
      shift(O(0), MI->getOperand(2).getImm() * (Op == Potados::SHLi ? -1 : 1),
            Op == Potados::SRAi);
      return;
    case Potados::SHLr:
      inst("NEG R6, " + O(2));
      inst("SH " + O(0) + ", R6, 0");
      return;
    case Potados::SRLr:
    case Potados::SRAr:
      inst(Twine(Op == Potados::SRAr ? "ASH " : "SH ") + O(0) + ", " + O(2) +
           ", 0");
      return;
    case Potados::LD16:
    case Potados::ST16:
      inst(Twine(Op == Potados::LD16 ? "LD " : "ST ") + O(0) + ", [" + O(1) +
           "]");
      return;
    case Potados::LDprivate:
    case Potados::STprivate:
      // LLVM's private legalization tables retain octet-based offsets. Their
      // backing storage is in RAM; only the final bus transaction counts cells.
      mov("R6", O(1));
      shift("R6", 1);
      inst(Twine(Op == Potados::LDprivate ? "LD " : "ST ") + O(0) + ", [R6]");
      return;
    case Potados::LDsp:
    case Potados::STsp:
      stackAccess(Op == Potados::LDsp, O(0), MI->getOperand(1).getImm());
      return;
    case Potados::LEAsp:
    case Potados::LEAspPrivate:
      mov(O(0), "SP");
      if (Op == Potados::LEAspPrivate)
        shift(O(0), -1);
      if (MI->getOperand(1).getImm()) {
        if (MI->getOperand(1).getImm() & 1)
          report_fatal_error("unaligned POTADOS backing object");
        inst("LI R6, " + Twine(MI->getOperand(1).getImm() /
                               (Op == Potados::LEAspPrivate ? 1 : 2)));
        inst("ADD " + O(0) + ", " + O(0) + ", R6");
      }
      return;
    case Potados::ADJSP:
      adjustSP(MI->getOperand(0).getImm());
      return;
    case Potados::BR:
      inst("JMP " + O(0));
      return;
    case Potados::BRCC: {
      std::string A = O(0), B = O(1),
                  C = compare(MI->getOperand(3).getImm(), A, B, true);
      inst(C + " " + A + ", " + B + ", " + O(2));
      return;
    }
    case Potados::SETCC: {
      std::string A = O(1), B = O(2),
                  C = compare(MI->getOperand(3).getImm(), A, B, false);
      inst(C + " " + O(0) + ", " + A + ", " + B);
      return;
    }
    case Potados::SELECT: {
      auto Done = label("select");
      inst("JE " + O(1) + ", ZERO, " + Done);
      mov(O(0), O(2));
      text(Done + ":");
      return;
    }
    case Potados::CALLg:
      inst("JAL R7, " + O(0));
      return;
    case Potados::CALLr:
      inst("JALR R7, " + O(0));
      return;
    case Potados::RET:
      inst("JMPR R7");
      return;
    default:
      report_fatal_error(Twine("unexpanded POTADOS machine instruction: ") +
                         MF->getSubtarget().getInstrInfo()->getName(Op));
    }
  }
};
} // namespace
char PotadosAsmPrinter::ID;
INITIALIZE_PASS(PotadosAsmPrinter, DEBUG_TYPE, "POTADOS assembly printer",
                false, false)
extern "C" LLVM_EXTERNAL_VISIBILITY void LLVMInitializePotadosAsmPrinter() {
  RegisterAsmPrinter<PotadosAsmPrinter> X(getThePotadosTarget());
}
