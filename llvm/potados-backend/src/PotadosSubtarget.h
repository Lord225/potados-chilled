#ifndef LLVM_Potados_SUBTARGET_H
#define LLVM_Potados_SUBTARGET_H

#include "Potados.h"
#include "PotadosFrameLowering.h"
#include "PotadosISelLowering.h"
#include "PotadosInstrInfo.h"
#include "PotadosSelectionDAGInfo.h"
#include "llvm/CodeGen/TargetSubtargetInfo.h"

#define GET_SUBTARGETINFO_HEADER
#include "PotadosGenSubtargetInfo.inc"

namespace llvm {
class PotadosSubtarget final : public PotadosGenSubtargetInfo {
  PotadosInstrInfo InstrInfo;
  PotadosTargetLowering TLInfo;
  PotadosFrameLowering FrameLowering;
  PotadosSelectionDAGInfo TSInfo;

public:
  PotadosSubtarget(const Triple &TT, StringRef CPU, StringRef FS,
                   const TargetMachine &TM);
  void ParseSubtargetFeatures(StringRef CPU, StringRef TuneCPU, StringRef FS);

  const PotadosInstrInfo *getInstrInfo() const override { return &InstrInfo; }
  const PotadosRegisterInfo *getRegisterInfo() const override {
    return &InstrInfo.getRegisterInfo();
  }
  const PotadosTargetLowering *getTargetLowering() const override {
    return &TLInfo;
  }
  const PotadosFrameLowering *getFrameLowering() const override {
    return &FrameLowering;
  }
  const SelectionDAGTargetInfo *getSelectionDAGInfo() const override {
    return &TSInfo;
  }
  void initLibcallLoweringInfo(LibcallLoweringInfo &Info) const override;
};
} // namespace llvm

#endif
