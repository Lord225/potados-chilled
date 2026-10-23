#include "Potados.h"
#include "llvm/MC/MCAsmInfo.h"
#include "llvm/MC/MCInstPrinter.h"
#include "llvm/MC/MCInstrInfo.h"
#include "llvm/MC/MCRegisterInfo.h"
#include "llvm/MC/MCSubtargetInfo.h"
#include "llvm/MC/TargetRegistry.h"
#include "llvm/TargetParser/Triple.h"
using namespace llvm;
#define GET_INSTRINFO_MC_DESC
#include "PotadosGenInstrInfo.inc"
#define GET_REGINFO_MC_DESC
#include "PotadosGenRegisterInfo.inc"
#define GET_SUBTARGETINFO_MC_DESC
#include "PotadosGenSubtargetInfo.inc"
namespace {
// All selected instructions are expanded to raw flat-assembler text by
// PotadosAsmPrinter. LLVM still requires an MC printer when creating an
// assembly streamer (for register names and inline-assembly substitutions).
class PotadosInstPrinter final : public MCInstPrinter {
public:
  PotadosInstPrinter(const MCAsmInfo &A, const MCInstrInfo &I,
                     const MCRegisterInfo &R)
      : MCInstPrinter(A, I, R) {}
  void printRegName(raw_ostream &OS, MCRegister Reg) override {
    OS << MRI.getName(Reg);
  }
  void printInst(const MCInst *, uint64_t, StringRef, const MCSubtargetInfo &,
                 raw_ostream &) override {
    llvm_unreachable("POTADOS instructions must pass through the flat printer");
  }
  std::pair<const char *, uint64_t> getMnemonic(const MCInst &) const override {
    return {"", 0};
  }
};
class PotadosAsmInfo final : public MCAsmInfo {
public:
  PotadosAsmInfo(const MCTargetOptions &O) : MCAsmInfo(O) {
    CodePointerSize = CalleeSaveStackSlotSize = 2;
    MinInstAlignment = 2;
    MaxInstLength = 4;
    CommentString = ";";
    SeparatorString = nullptr;
    InternalSymbolPrefix = "L";
    HasDotTypeDotSizeDirective = HasSingleParameterDotFile = HasIdentDirective =
        HasFunctionAlignment = false;
    UseIntegratedAssembler = false;
    SupportsDebugInformation = false;
  }
};
} // namespace
static MCInstrInfo *createII() {
  auto *I = new MCInstrInfo();
  InitPotadosMCInstrInfo(I);
  return I;
}
static MCRegisterInfo *createRI(const Triple &) {
  auto *R = new MCRegisterInfo();
  InitPotadosMCRegisterInfo(R, Potados::R7);
  return R;
}
static MCSubtargetInfo *createST(const Triple &T, StringRef CPU, StringRef FS) {
  if (CPU.empty())
    CPU = "generic";
  return createPotadosMCSubtargetInfoImpl(T, CPU, CPU, FS);
}
static MCAsmInfo *createAI(const MCRegisterInfo &, const Triple &,
                           const MCTargetOptions &O) {
  return new PotadosAsmInfo(O);
}
static MCInstPrinter *createPrinter(const Triple &, unsigned Variant,
                                    const MCAsmInfo &A, const MCInstrInfo &I,
                                    const MCRegisterInfo &R) {
  return Variant == 0 ? new PotadosInstPrinter(A, I, R) : nullptr;
}
extern "C" LLVM_EXTERNAL_VISIBILITY void LLVMInitializePotadosTargetMC() {
  auto &T = getThePotadosTarget();
  TargetRegistry::RegisterMCAsmInfo(T, createAI);
  TargetRegistry::RegisterMCInstrInfo(T, createII);
  TargetRegistry::RegisterMCRegInfo(T, createRI);
  TargetRegistry::RegisterMCSubtargetInfo(T, createST);
  TargetRegistry::RegisterMCInstPrinter(T, createPrinter);
}
