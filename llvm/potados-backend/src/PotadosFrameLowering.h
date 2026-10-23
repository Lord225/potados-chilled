#ifndef LLVM_Potados_FRAMELOWERING_H
#define LLVM_Potados_FRAMELOWERING_H

#include "llvm/CodeGen/TargetFrameLowering.h"

namespace llvm {
class PotadosFrameLowering final : public TargetFrameLowering {
protected:
  bool hasFPImpl(const MachineFunction &) const override { return false; }
  bool hasReservedCallFrame(const MachineFunction &MF) const override;

public:
  PotadosFrameLowering()
      : TargetFrameLowering(StackGrowsDown, Align(2), 0, Align(2)) {}

  void emitPrologue(MachineFunction &MF, MachineBasicBlock &MBB) const override;
  void emitEpilogue(MachineFunction &MF, MachineBasicBlock &MBB) const override;
  MachineBasicBlock::iterator
  eliminateCallFramePseudoInstr(MachineFunction &MF, MachineBasicBlock &MBB,
                                MachineBasicBlock::iterator I) const override;
};
} // namespace llvm

#endif
