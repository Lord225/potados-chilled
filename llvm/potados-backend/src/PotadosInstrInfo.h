#ifndef LLVM_Potados_INSTRINFO_H
#define LLVM_Potados_INSTRINFO_H

#include "PotadosRegisterInfo.h"
#include "llvm/CodeGen/TargetInstrInfo.h"

#define GET_INSTRINFO_HEADER
#include "PotadosGenInstrInfo.inc"

namespace llvm {
class PotadosSubtarget;

class PotadosInstrInfo final : public PotadosGenInstrInfo {
  PotadosRegisterInfo RI;

public:
  explicit PotadosInstrInfo(const PotadosSubtarget &STI);
  const PotadosRegisterInfo &getRegisterInfo() const { return RI; }

  void copyPhysReg(MachineBasicBlock &MBB, MachineBasicBlock::iterator I,
                   const DebugLoc &DL, Register DestReg, Register SrcReg,
                   bool KillSrc, bool RenamableDest = false,
                   bool RenamableSrc = false) const override;
  void storeRegToStackSlot(MachineBasicBlock &MBB,
                           MachineBasicBlock::iterator MI, Register SrcReg,
                           bool IsKill, int FrameIndex,
                           const TargetRegisterClass *RC, Register VReg,
                           MachineInstr::MIFlag Flags) const override;
  void loadRegFromStackSlot(MachineBasicBlock &MBB,
                            MachineBasicBlock::iterator MI, Register DestReg,
                            int FrameIndex, const TargetRegisterClass *RC,
                            Register VReg, unsigned SubReg,
                            MachineInstr::MIFlag Flags) const override;
  bool expandPostRAPseudo(MachineInstr &MI) const override;
  unsigned getInstSizeInBytes(const MachineInstr &MI) const override;
  bool analyzeBranch(MachineBasicBlock &MBB, MachineBasicBlock *&TBB,
                     MachineBasicBlock *&FBB,
                     SmallVectorImpl<MachineOperand> &Cond,
                     bool AllowModify = false) const override;
  unsigned removeBranch(MachineBasicBlock &MBB,
                        int *BytesRemoved = nullptr) const override;
  unsigned insertBranch(MachineBasicBlock &MBB, MachineBasicBlock *TBB,
                        MachineBasicBlock *FBB, ArrayRef<MachineOperand> Cond,
                        const DebugLoc &DL,
                        int *BytesAdded = nullptr) const override;
  bool
  reverseBranchCondition(SmallVectorImpl<MachineOperand> &Cond) const override;
};
} // namespace llvm

#endif
