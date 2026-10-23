#ifndef LLVM_POTADOS_ISELLOWERING_H
#define LLVM_POTADOS_ISELLOWERING_H
#include "Potados.h"
#include "llvm/CodeGen/SelectionDAG.h"
#include "llvm/CodeGen/TargetLowering.h"
namespace llvm {
class PotadosSubtarget;
class PotadosTargetLowering final : public TargetLowering {
public:
  PotadosTargetLowering(const TargetMachine &, const PotadosSubtarget &);
  MVT getScalarShiftAmountTy(const DataLayout &, EVT) const override {
    return MVT::i16;
  }
  EVT getSetCCResultType(const DataLayout &, LLVMContext &,
                         EVT) const override {
    return MVT::i16;
  }
  const char *getTargetNodeName(unsigned) const override;
  SDValue LowerOperation(SDValue, SelectionDAG &) const override;
  ConstraintType getConstraintType(StringRef) const override;
  std::pair<unsigned, const TargetRegisterClass *>
  getRegForInlineAsmConstraint(const TargetRegisterInfo *, StringRef,
                               MVT) const override;

private:
  SDValue LowerFormalArguments(SDValue, CallingConv::ID, bool,
                               const SmallVectorImpl<ISD::InputArg> &,
                               const SDLoc &, SelectionDAG &,
                               SmallVectorImpl<SDValue> &) const override;
  SDValue LowerReturn(SDValue, CallingConv::ID, bool,
                      const SmallVectorImpl<ISD::OutputArg> &,
                      const SmallVectorImpl<SDValue> &, const SDLoc &,
                      SelectionDAG &) const override;
  SDValue LowerCall(CallLoweringInfo &,
                    SmallVectorImpl<SDValue> &) const override;
};
} // namespace llvm
#endif
