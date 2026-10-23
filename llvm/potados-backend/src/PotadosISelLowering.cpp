#include "PotadosISelLowering.h"
#include "PotadosSubtarget.h"
#include "llvm/CodeGen/MachineFrameInfo.h"
#include "llvm/CodeGen/MachineFunction.h"
#include "llvm/CodeGen/MachineRegisterInfo.h"
#include "llvm/Support/ErrorHandling.h"
using namespace llvm;
static constexpr MCPhysReg ArgRegs[] = {Potados::R2, Potados::R3, Potados::R4,
                                        Potados::R5};
static void checkABI(CallingConv::ID CC, bool VarArg) {
  if ((CC != CallingConv::C && CC != CallingConv::Fast) || VarArg)
    report_fatal_error("POTADOS supports non-variadic C/fast calls only");
}
PotadosTargetLowering::PotadosTargetLowering(const TargetMachine &TM,
                                             const PotadosSubtarget &STI)
    : TargetLowering(TM, STI) {
  addRegisterClass(MVT::i16, &Potados::GPRRegClass);
  computeRegisterProperties(STI.getRegisterInfo());
  setStackPointerRegisterToSaveRestore(Potados::SP);
  setBooleanContents(ZeroOrOneBooleanContent);
  setMinFunctionAlignment(Align(2));
  setPrefFunctionAlignment(Align(2));
  setMaxAtomicSizeInBitsSupported(0);
  setMinimumJumpTableEntries(~0u);
  MaxStoresPerMemset = MaxStoresPerMemcpy = MaxStoresPerMemmove = 32;
  for (unsigned Op : {ISD::BR_CC, ISD::SETCC, ISD::GlobalAddress,
                      ISD::ExternalSymbol, ISD::UMUL_LOHI})
    setOperationAction(Op, MVT::i16, Custom);
  setOperationAction(ISD::BRCOND, MVT::Other, Expand);
  setOperationAction(ISD::SELECT_CC, MVT::i16, Expand);
  setOperationAction(ISD::SELECT, MVT::i16, Legal);
  for (unsigned Op :
       {ISD::ROTL, ISD::ROTR, ISD::FSHL, ISD::FSHR, ISD::SHL_PARTS,
        ISD::SRL_PARTS, ISD::SRA_PARTS, ISD::SMUL_LOHI, ISD::MULHU, ISD::MULHS,
        ISD::BSWAP, ISD::BITREVERSE, ISD::CTLZ, ISD::CTTZ, ISD::CTPOP,
        ISD::SIGN_EXTEND_INREG})
    setOperationAction(Op, MVT::i16, Expand);
  for (unsigned Op : {ISD::SDIV, ISD::UDIV, ISD::SREM, ISD::UREM})
    setOperationAction(Op, MVT::i16, LibCall);
  setOperationAction(ISD::SDIVREM, MVT::i16, Expand);
  setOperationAction(ISD::UDIVREM, MVT::i16, Expand);
  // SIGN_EXTEND_INREG is legalized using the inner type, unlike most ops.
  setOperationAction(ISD::SIGN_EXTEND_INREG, MVT::i1, Expand);
  setOperationAction(ISD::SIGN_EXTEND_INREG, MVT::i8, Expand);
  setTruncStoreAction(MVT::i16, MVT::i8, Legal);
  for (unsigned Ext : {ISD::EXTLOAD, ISD::ZEXTLOAD, ISD::SEXTLOAD})
    setLoadExtAction(Ext, MVT::i16, MVT::i8, Legal);
}
const char *PotadosTargetLowering::getTargetNodeName(unsigned Op) const {
  switch (Op) {
  case PotadosISD::RET:
    return "PotadosISD::RET";
  case PotadosISD::CALL:
    return "PotadosISD::CALL";
  case PotadosISD::BR_CC:
    return "PotadosISD::BR_CC";
  case PotadosISD::SETCC:
    return "PotadosISD::SETCC";
  case PotadosISD::ADDRESS:
    return "PotadosISD::ADDRESS";
  case PotadosISD::LOAD_WORD:
    return "PotadosISD::LOAD_WORD";
  case PotadosISD::STORE_WORD:
    return "PotadosISD::STORE_WORD";
  default:
    return nullptr;
  }
}
SDValue PotadosTargetLowering::LowerOperation(SDValue Op,
                                              SelectionDAG &DAG) const {
  SDLoc DL(Op);
  switch (Op.getOpcode()) {
  case ISD::GlobalAddress: {
    auto *G = cast<GlobalAddressSDNode>(Op);
    return DAG.getTargetGlobalAddress(G->getGlobal(), DL, MVT::i16,
                                      G->getOffset());
  }
  case ISD::ExternalSymbol:
    return DAG.getTargetExternalSymbol(
        cast<ExternalSymbolSDNode>(Op)->getSymbol(), MVT::i16);
  case ISD::BR_CC:
    return DAG.getNode(
        PotadosISD::BR_CC, DL, MVT::Other, Op.getOperand(0), Op.getOperand(2),
        Op.getOperand(3), Op.getOperand(4),
        DAG.getConstant(cast<CondCodeSDNode>(Op.getOperand(1))->get(), DL,
                        MVT::i16));
  case ISD::SETCC:
    return DAG.getNode(
        PotadosISD::SETCC, DL, MVT::i16, Op.getOperand(0), Op.getOperand(1),
        DAG.getConstant(cast<CondCodeSDNode>(Op.getOperand(2))->get(), DL,
                        MVT::i16));
  case ISD::UMUL_LOHI: {
    auto C = [&](unsigned V) { return DAG.getConstant(V, DL, MVT::i16); };
    auto N = [&](unsigned Opc, SDValue A, SDValue B) {
      return DAG.getNode(Opc, DL, MVT::i16, A, B);
    };
    SDValue A = Op.getOperand(0), B = Op.getOperand(1);
    SDValue AL = N(ISD::AND, A, C(255)), AH = N(ISD::SRL, A, C(8));
    SDValue BL = N(ISD::AND, B, C(255)), BH = N(ISD::SRL, B, C(8));
    SDValue P0 = N(ISD::MUL, AL, BL), P1 = N(ISD::MUL, AL, BH);
    SDValue P2 = N(ISD::MUL, AH, BL), P3 = N(ISD::MUL, AH, BH);
    SDValue T =
        N(ISD::ADD, N(ISD::SRL, P0, C(8)),
          N(ISD::ADD, N(ISD::AND, P1, C(255)), N(ISD::AND, P2, C(255))));
    SDValue Lo = N(ISD::OR, N(ISD::AND, P0, C(255)), N(ISD::SHL, T, C(8)));
    SDValue Hi = N(ISD::ADD, P3,
                   N(ISD::ADD, N(ISD::SRL, P1, C(8)),
                     N(ISD::ADD, N(ISD::SRL, P2, C(8)), N(ISD::SRL, T, C(8)))));
    return DAG.getMergeValues({Lo, Hi}, DL);
  }
  default:
    report_fatal_error("unsupported custom POTADOS operation");
  }
}
SDValue PotadosTargetLowering::LowerFormalArguments(
    SDValue Chain, CallingConv::ID CC, bool VarArg,
    const SmallVectorImpl<ISD::InputArg> &Ins, const SDLoc &DL,
    SelectionDAG &DAG, SmallVectorImpl<SDValue> &InVals) const {
  checkABI(CC, VarArg);
  auto &MRI = DAG.getMachineFunction().getRegInfo();
  auto &MFI = DAG.getMachineFunction().getFrameInfo();
  for (unsigned I = 0; I < Ins.size(); ++I) {
    if (Ins[I].VT != MVT::i16 || Ins[I].Flags.isByVal())
      report_fatal_error("unsupported POTADOS by-value argument");
    if (I < std::size(ArgRegs)) {
      Register V = MRI.createVirtualRegister(&Potados::GPRRegClass);
      MRI.addLiveIn(ArgRegs[I], V);
      InVals.push_back(DAG.getCopyFromReg(Chain, DL, V, MVT::i16));
    } else {
      int FI = MFI.CreateFixedObject(2, (I - std::size(ArgRegs)) * 2, true);
      SDValue V = DAG.getLoad(
          MVT::i16, DL, Chain, DAG.getFrameIndex(FI, MVT::i16),
          MachinePointerInfo::getFixedStack(DAG.getMachineFunction(), FI));
      InVals.push_back(V);
      Chain = V.getValue(1);
    }
  }
  return Chain;
}
SDValue
PotadosTargetLowering::LowerReturn(SDValue Chain, CallingConv::ID CC,
                                   bool VarArg,
                                   const SmallVectorImpl<ISD::OutputArg> &Outs,
                                   const SmallVectorImpl<SDValue> &Vals,
                                   const SDLoc &DL, SelectionDAG &DAG) const {
  checkABI(CC, VarArg);
  if (Outs.size() > std::size(ArgRegs))
    report_fatal_error("POTADOS return value exceeds 64 bits");
  SmallVector<SDValue, 6> Ops = {Chain};
  SDValue Glue;
  for (unsigned I = 0; I < Outs.size(); ++I) {
    Chain = DAG.getCopyToReg(Chain, DL, ArgRegs[I], Vals[I], Glue);
    Glue = Chain.getValue(1);
    Ops[0] = Chain;
    Ops.push_back(DAG.getRegister(ArgRegs[I], MVT::i16));
  }
  if (Glue)
    Ops.push_back(Glue);
  return DAG.getNode(PotadosISD::RET, DL, MVT::Other, Ops);
}
SDValue
PotadosTargetLowering::LowerCall(CallLoweringInfo &CLI,
                                 SmallVectorImpl<SDValue> &InVals) const {
  checkABI(CLI.CallConv, CLI.IsVarArg);
  CLI.IsTailCall = false;
  SelectionDAG &DAG = CLI.DAG;
  SDLoc DL = CLI.DL;
  StringRef CalleeName;
  if (auto *G = dyn_cast<GlobalAddressSDNode>(CLI.Callee))
    CalleeName = G->getGlobal()->getName();
  else if (auto *E = dyn_cast<ExternalSymbolSDNode>(CLI.Callee))
    CalleeName = E->getSymbol();
  if (CalleeName == "__potados_address") {
    if (CLI.OutVals.size() != 1 || CLI.Ins.size() != 1)
      report_fatal_error("invalid POTADOS address operation signature");
    // Do not expose frame/global alignment to KnownBits: native cell addresses
    // may be odd even when their private LLVM objects have two-octet alignment.
    InVals.push_back(
        DAG.getNode(PotadosISD::ADDRESS, DL, MVT::i16, CLI.OutVals[0]));
    return CLI.Chain;
  }
  bool WordLoad = CalleeName == "__potados_load_word" ||
                  CalleeName == "__potados_load_volatile_word";
  bool WordStore = CalleeName == "__potados_store_word" ||
                   CalleeName == "__potados_store_volatile_word";
  if (WordLoad || WordStore) {
    if (CLI.OutVals.size() != (WordLoad ? 1u : 2u) ||
        CLI.Ins.size() != (WordLoad ? 1u : 0u))
      report_fatal_error("invalid POTADOS native memory operation signature");
    auto Flags =
        WordLoad ? MachineMemOperand::MOLoad : MachineMemOperand::MOStore;
    if (CalleeName.contains("volatile"))
      Flags |= MachineMemOperand::MOVolatile;
    SmallVector<SDValue, 3> Ops = {CLI.Chain, CLI.OutVals[0]};
    if (WordStore)
      Ops.push_back(CLI.OutVals[1]);
    SDValue Mem = DAG.getMemIntrinsicNode(
        WordLoad ? PotadosISD::LOAD_WORD : PotadosISD::STORE_WORD, DL,
        WordLoad ? DAG.getVTList(MVT::i16, MVT::Other)
                 : DAG.getVTList(MVT::Other),
        Ops, MVT::i16, MachinePointerInfo(), Align(1), Flags,
        LocationSize::precise(2));
    if (WordLoad) {
      InVals.push_back(Mem);
      return Mem.getValue(1);
    }
    return Mem;
  }
  unsigned Bytes = CLI.OutVals.size() > std::size(ArgRegs)
                       ? (CLI.OutVals.size() - std::size(ArgRegs)) * 2
                       : 0;
  SDValue Chain = DAG.getCALLSEQ_START(CLI.Chain, Bytes, 0, DL), Glue;
  for (unsigned I = std::size(ArgRegs); I < CLI.OutVals.size(); ++I) {
    SDValue SP = DAG.getCopyFromReg(Chain, DL, Potados::SP, MVT::i16);
    Chain = SP.getValue(1);
    // The reserved LLVM call frame counts octets; its native SP counts cells.
    SDValue Ptr = SP;
    Ptr = DAG.getNode(ISD::ADD, DL, MVT::i16, Ptr,
                      DAG.getConstant(I - std::size(ArgRegs), DL, MVT::i16));
    Chain = DAG.getMemIntrinsicNode(
        PotadosISD::STORE_WORD, DL, DAG.getVTList(MVT::Other),
        {Chain, Ptr, CLI.OutVals[I]}, MVT::i16, MachinePointerInfo(), Align(1),
        MachineMemOperand::MOStore, LocationSize::precise(2));
  }
  SmallVector<SDValue, 10> Ops;
  SDValue Callee = CLI.Callee;
  if (auto *G = dyn_cast<GlobalAddressSDNode>(Callee))
    Callee = DAG.getTargetGlobalAddress(G->getGlobal(), DL, MVT::i16,
                                        G->getOffset());
  else if (auto *E = dyn_cast<ExternalSymbolSDNode>(Callee))
    Callee = DAG.getTargetExternalSymbol(E->getSymbol(), MVT::i16);
  else {
    // Four argument words occupy every allocatable register. Move an
    // indirect target into the reserved link register before those glued
    // copies, freeing its GPR. JALR reads its target before writing its link.
    Chain = DAG.getCopyToReg(Chain, DL, Potados::R7, Callee, Glue);
    Glue = Chain.getValue(1);
    Callee = DAG.getRegister(Potados::R7, MVT::i16);
  }
  Ops = {Chain, Callee};
  for (unsigned I = 0;
       I < std::min<unsigned>(CLI.OutVals.size(), std::size(ArgRegs)); ++I) {
    if (CLI.Outs[I].Flags.isByVal())
      report_fatal_error("POTADOS does not support by-value aggregate calls");
    Chain = DAG.getCopyToReg(Chain, DL, ArgRegs[I], CLI.OutVals[I], Glue);
    Glue = Chain.getValue(1);
    Ops.push_back(DAG.getRegister(ArgRegs[I], MVT::i16));
  }
  Ops[0] = Chain;
  if (Glue)
    Ops.push_back(Glue);
  Chain = DAG.getNode(PotadosISD::CALL, DL,
                      DAG.getVTList(MVT::Other, MVT::Glue), Ops);
  Chain = DAG.getCALLSEQ_END(Chain, Bytes, 0, Chain.getValue(1), DL);
  Glue = Chain.getValue(1);
  if (CLI.Ins.size() > std::size(ArgRegs))
    report_fatal_error("POTADOS call result exceeds 64 bits");
  for (unsigned I = 0; I < CLI.Ins.size(); ++I) {
    SDValue V = DAG.getCopyFromReg(Chain, DL, ArgRegs[I], MVT::i16, Glue);
    InVals.push_back(V);
    Chain = V.getValue(1);
    Glue = V.getValue(2);
  }
  return Chain;
}
TargetLowering::ConstraintType
PotadosTargetLowering::getConstraintType(StringRef C) const {
  return C == "r" ? C_RegisterClass : TargetLowering::getConstraintType(C);
}
std::pair<unsigned, const TargetRegisterClass *>
PotadosTargetLowering::getRegForInlineAsmConstraint(
    const TargetRegisterInfo *TRI, StringRef C, MVT VT) const {
  if (C == "r" && VT == MVT::i16)
    return {0, &Potados::GPRRegClass};
  return TargetLowering::getRegForInlineAsmConstraint(TRI, C, VT);
}
