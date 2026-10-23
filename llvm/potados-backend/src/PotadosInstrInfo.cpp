#include "PotadosInstrInfo.h"
#include "PotadosSubtarget.h"
#include "llvm/CodeGen/MachineInstrBuilder.h"
#include "llvm/Support/ErrorHandling.h"
using namespace llvm;
#define GET_INSTRINFO_CTOR_DTOR
#include "PotadosGenInstrInfo.inc"
PotadosInstrInfo::PotadosInstrInfo(const PotadosSubtarget &STI)
    : PotadosGenInstrInfo(STI, RI, Potados::ADJCALLSTACKDOWN,
                          Potados::ADJCALLSTACKUP),
      RI() {}
void PotadosInstrInfo::copyPhysReg(MachineBasicBlock &MBB,
                                   MachineBasicBlock::iterator I,
                                   const DebugLoc &DL, Register Dest,
                                   Register Src, bool Kill, bool, bool) const {
  BuildMI(MBB, I, DL, get(Potados::MOV), Dest)
      .addReg(Src, getKillRegState(Kill));
}
void PotadosInstrInfo::storeRegToStackSlot(MachineBasicBlock &MBB,
                                           MachineBasicBlock::iterator I,
                                           Register Src, bool Kill, int FI,
                                           const TargetRegisterClass *,
                                           Register,
                                           MachineInstr::MIFlag Flags) const {
  BuildMI(MBB, I, DebugLoc(), get(Potados::STfi))
      .addReg(Src, getKillRegState(Kill))
      .addFrameIndex(FI)
      .addImm(0)
      .setMIFlag(Flags);
}
void PotadosInstrInfo::loadRegFromStackSlot(MachineBasicBlock &MBB,
                                            MachineBasicBlock::iterator I,
                                            Register Dst, int FI,
                                            const TargetRegisterClass *,
                                            Register, unsigned SubReg,
                                            MachineInstr::MIFlag Flags) const {
  if (SubReg)
    report_fatal_error("POTADOS has no subregister spill loads");
  BuildMI(MBB, I, DebugLoc(), get(Potados::LDfi), Dst)
      .addFrameIndex(FI)
      .addImm(0)
      .setMIFlag(Flags);
}
bool PotadosInstrInfo::expandPostRAPseudo(MachineInstr &) const {
  return false;
}
unsigned PotadosInstrInfo::getInstSizeInBytes(const MachineInstr &) const {
  return 2;
}
