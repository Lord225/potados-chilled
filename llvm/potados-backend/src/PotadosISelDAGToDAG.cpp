#include "Potados.h"
#include "PotadosTargetMachine.h"
#include "llvm/CodeGen/SelectionDAGISel.h"
#include "llvm/InitializePasses.h"
#include "llvm/Support/KnownBits.h"
using namespace llvm;
#define DEBUG_TYPE "potados-isel"
namespace {
class PotadosISel final : public SelectionDAGISel {
public:
  PotadosISel(PotadosTargetMachine &TM, CodeGenOptLevel OL)
      : SelectionDAGISel(TM, OL) {}
  SDValue materialize(SDValue V, const SDLoc &DL) {
    if (V.getOpcode() == ISD::TargetGlobalAddress ||
        V.getOpcode() == ISD::TargetExternalSymbol)
      return SDValue(CurDAG->getMachineNode(Potados::LIga, DL, MVT::i16, V), 0);
    if (V.getOpcode() == ISD::FrameIndex)
      return SDValue(CurDAG->getMachineNode(
                         Potados::LEAfiPrivate, DL, MVT::i16,
                         CurDAG->getTargetFrameIndex(
                             cast<FrameIndexSDNode>(V)->getIndex(), MVT::i16),
                         CurDAG->getTargetConstant(0, DL, MVT::i16)),
                     0);
    return V;
  }
  void Select(SDNode *N) override {
    if (N->isMachineOpcode()) {
      N->setNodeId(-1);
      return;
    }
    SDLoc DL(N);
    // Target symbols are immediate operands for CALLg/LIga, but every other
    // use needs an actual register before the generated matcher runs.
    SmallVector<SDValue, 8> Ops(N->op_begin(), N->op_end());
    auto MaterializeAt = [&](unsigned I) { Ops[I] = materialize(Ops[I], DL); };
    if (N->getOpcode() == ISD::CopyToReg)
      MaterializeAt(2);
    if (N->getOpcode() == ISD::SELECT) {
      MaterializeAt(1);
      MaterializeAt(2);
    }
    if (N->getOpcode() == PotadosISD::SETCC) {
      MaterializeAt(0);
      MaterializeAt(1);
    }
    if (N->getOpcode() == PotadosISD::BR_CC) {
      MaterializeAt(1);
      MaterializeAt(2);
    }
    bool Binary = false;
    switch (N->getOpcode()) {
    case ISD::ADD:
    case ISD::SUB:
    case ISD::AND:
    case ISD::OR:
    case ISD::XOR:
    case ISD::MUL:
    case ISD::SHL:
    case ISD::SRL:
    case ISD::SRA:
      Binary = true;
      MaterializeAt(0);
      MaterializeAt(1);
      break;
    }
    if (N->getOpcode() == ISD::CopyToReg || N->getOpcode() == ISD::SELECT ||
        N->getOpcode() == PotadosISD::SETCC ||
        N->getOpcode() == PotadosISD::BR_CC || Binary)
      CurDAG->UpdateNodeOperands(N, Ops);
    switch (N->getOpcode()) {
    case PotadosISD::ADDRESS: {
      // Only this operation converts a private backing object into a native C
      // pointer. Other frame-index users belong to LLVM legalization and must
      // retain octet offsets until their private load/store is selected.
      if (N->getOperand(0).getOpcode() == ISD::FrameIndex) {
        SDValue FI = CurDAG->getTargetFrameIndex(
            cast<FrameIndexSDNode>(N->getOperand(0))->getIndex(), MVT::i16);
        CurDAG->SelectNodeTo(N, Potados::LEAfi, MVT::i16, FI,
                             CurDAG->getTargetConstant(0, DL, MVT::i16));
        return;
      }
      SDValue Ptr = materialize(N->getOperand(0), DL);
      CurDAG->SelectNodeTo(N, Potados::MOV, MVT::i16, Ptr);
      return;
    }
    case PotadosISD::LOAD_WORD:
    case PotadosISD::STORE_WORD: {
      auto *Mem = cast<MemSDNode>(N);
      bool Load = N->getOpcode() == PotadosISD::LOAD_WORD;
      SDValue Ptr = materialize(N->getOperand(1), DL);
      SmallVector<SDValue, 3> MemOps;
      if (!Load)
        MemOps.push_back(materialize(N->getOperand(2), DL));
      MemOps.push_back(Ptr);
      MemOps.push_back(N->getOperand(0));
      MachineMemOperand *MMO = Mem->getMemOperand();
      SDNode *Selected =
          CurDAG->SelectNodeTo(N, Load ? Potados::LD16 : Potados::ST16,
                               Load ? CurDAG->getVTList(MVT::i16, MVT::Other)
                                    : CurDAG->getVTList(MVT::Other),
                               MemOps);
      CurDAG->setNodeMemRefs(cast<MachineSDNode>(Selected), {MMO});
      return;
    }
    case ISD::MUL:
      if (CurDAG->computeKnownBits(N->getOperand(0)).getMaxValue().ule(255) &&
          CurDAG->computeKnownBits(N->getOperand(1)).getMaxValue().ule(255)) {
        CurDAG->SelectNodeTo(N, Potados::MUL8, MVT::i16, N->getOperand(0),
                             N->getOperand(1));
        return;
      }
      break;
    case ISD::FrameIndex: {
      SDValue FI = CurDAG->getTargetFrameIndex(
          cast<FrameIndexSDNode>(N)->getIndex(), MVT::i16);
      CurDAG->SelectNodeTo(N, Potados::LEAfiPrivate, MVT::i16, FI,
                           CurDAG->getTargetConstant(0, DL, MVT::i16));
      return;
    }
    case ISD::LOAD: {
      auto *L = cast<LoadSDNode>(N);
      if (L->getMemoryVT() != MVT::i16)
        report_fatal_error("POTADOS native C storage requires 16-bit cells");
      SDValue Ptr = L->getBasePtr();
      if (L->getMemoryVT() == MVT::i16 && Ptr.getOpcode() == ISD::FrameIndex) {
        SDValue FI = CurDAG->getTargetFrameIndex(
            cast<FrameIndexSDNode>(Ptr)->getIndex(), MVT::i16);
        CurDAG->SelectNodeTo(
            N, Potados::LDfi, MVT::i16, MVT::Other,
            {FI, CurDAG->getTargetConstant(0, DL, MVT::i16), L->getChain()});
      } else {
        Ptr = materialize(Ptr, DL);
        CurDAG->SelectNodeTo(N, Potados::LDprivate, MVT::i16, MVT::Other,
                             {Ptr, L->getChain()});
      }
      return;
    }
    case ISD::STORE: {
      auto *S = cast<StoreSDNode>(N);
      if (S->getMemoryVT() != MVT::i16)
        report_fatal_error("POTADOS native C storage requires 16-bit cells");
      SDValue Ptr = S->getBasePtr();
      SDValue Value = materialize(S->getValue(), DL);
      if (S->getMemoryVT() == MVT::i16 && Ptr.getOpcode() == ISD::FrameIndex) {
        SDValue FI = CurDAG->getTargetFrameIndex(
            cast<FrameIndexSDNode>(Ptr)->getIndex(), MVT::i16);
        CurDAG->SelectNodeTo(N, Potados::STfi, MVT::Other,
                             {Value, FI,
                              CurDAG->getTargetConstant(0, DL, MVT::i16),
                              S->getChain()});
      } else {
        Ptr = materialize(Ptr, DL);
        CurDAG->SelectNodeTo(N, Potados::STprivate, MVT::Other, Value, Ptr,
                             S->getChain());
      }
      return;
    }
    case ISD::SHL:
    case ISD::SRL:
    case ISD::SRA:
      if (auto *Amount = dyn_cast<ConstantSDNode>(N->getOperand(1))) {
        unsigned Op = N->getOpcode() == ISD::SHL   ? Potados::SHLi
                      : N->getOpcode() == ISD::SRL ? Potados::SRLi
                                                   : Potados::SRAi;
        CurDAG->SelectNodeTo(
            N, Op, MVT::i16, N->getOperand(0),
            CurDAG->getTargetConstant(Amount->getZExtValue(), DL, MVT::i16));
        return;
      }
      break;
    }
    SelectCode(N);
  }
#include "PotadosGenDAGISel.inc"
};
class PotadosDAGToDAGISelLegacy final : public SelectionDAGISelLegacy {
public:
  static char ID;
  PotadosDAGToDAGISelLegacy(PotadosTargetMachine &TM, CodeGenOptLevel OL)
      : SelectionDAGISelLegacy(ID, std::make_unique<PotadosISel>(TM, OL)) {}
};
} // namespace
char PotadosDAGToDAGISelLegacy::ID;
INITIALIZE_PASS(PotadosDAGToDAGISelLegacy, DEBUG_TYPE,
                "POTADOS DAG instruction selection", false, false)
FunctionPass *llvm::createPotadosISelDag(PotadosTargetMachine &TM,
                                         CodeGenOptLevel OL) {
  return new PotadosDAGToDAGISelLegacy(TM, OL);
}
