#include "PotadosFrameLowering.h"
#include "Potados.h"
#include "llvm/CodeGen/MachineFrameInfo.h"
#include "llvm/CodeGen/MachineFunction.h"
#include "llvm/CodeGen/MachineInstrBuilder.h"
#include "llvm/CodeGen/TargetInstrInfo.h"
#include "llvm/CodeGen/TargetSubtargetInfo.h"
#include "llvm/Support/ErrorHandling.h"
using namespace llvm;
bool PotadosFrameLowering::hasReservedCallFrame(
    const MachineFunction &MF) const {
  return !MF.getFrameInfo().hasVarSizedObjects();
}
void PotadosFrameLowering::emitPrologue(MachineFunction &MF,
                                        MachineBasicBlock &MBB) const {
  const auto &MFI = MF.getFrameInfo();
  if (MFI.getMaxAlign() > Align(2))
    report_fatal_error(
        "POTADOS does not support stack alignment greater than two bytes");
  if (MFI.hasVarSizedObjects())
    report_fatal_error("POTADOS does not support dynamic alloca");
  if (MFI.getStackSize()) {
    auto I = MBB.begin();
    const auto &TII = *MF.getSubtarget().getInstrInfo();
    BuildMI(MBB, I, DebugLoc(), TII.get(Potados::ADJSP))
        .addImm(-int64_t(MFI.getStackSize()))
        .setMIFlag(MachineInstr::FrameSetup);
  }
}
void PotadosFrameLowering::emitEpilogue(MachineFunction &MF,
                                        MachineBasicBlock &MBB) const {
  if (MF.getFrameInfo().getStackSize()) {
    const auto &TII = *MF.getSubtarget().getInstrInfo();
    BuildMI(MBB, MBB.getFirstTerminator(), DebugLoc(), TII.get(Potados::ADJSP))
        .addImm(MF.getFrameInfo().getStackSize())
        .setMIFlag(MachineInstr::FrameDestroy);
  }
}
MachineBasicBlock::iterator PotadosFrameLowering::eliminateCallFramePseudoInstr(
    MachineFunction &, MachineBasicBlock &MBB,
    MachineBasicBlock::iterator I) const {
  return MBB.erase(I);
}
