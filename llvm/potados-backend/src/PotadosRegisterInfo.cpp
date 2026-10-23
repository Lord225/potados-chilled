#include "PotadosRegisterInfo.h"
#include "Potados.h"
#include "PotadosFrameLowering.h"
#include "llvm/ADT/BitVector.h"
#include "llvm/CodeGen/MachineFrameInfo.h"
#include "llvm/CodeGen/MachineFunction.h"
#include "llvm/CodeGen/TargetInstrInfo.h"
#include "llvm/CodeGen/TargetSubtargetInfo.h"
#include "llvm/Support/ErrorHandling.h"
using namespace llvm;
#define GET_REGINFO_TARGET_DESC
#include "PotadosGenRegisterInfo.inc"
PotadosRegisterInfo::PotadosRegisterInfo()
    : PotadosGenRegisterInfo(Potados::R7) {}
const MCPhysReg *
PotadosRegisterInfo::getCalleeSavedRegs(const MachineFunction *) const {
  static const MCPhysReg Saved[] = {Potados::R7, 0};
  return Saved;
}
BitVector PotadosRegisterInfo::getReservedRegs(const MachineFunction &) const {
  BitVector R(getNumRegs());
  for (MCRegister Reg : {Potados::ZERO, Potados::SP, Potados::R6, Potados::R7})
    R.set(Reg);
  return R;
}
const TargetRegisterClass *
PotadosRegisterInfo::getPointerRegClass(unsigned) const {
  return &Potados::GPRRegClass;
}
bool PotadosRegisterInfo::eliminateFrameIndex(MachineBasicBlock::iterator II,
                                              int SPAdj, unsigned FIOperandNum,
                                              RegScavenger *) const {
  if (SPAdj)
    report_fatal_error("unexpected POTADOS call-frame adjustment");
  auto &MI = *II;
  const auto &MFI = MI.getMF()->getFrameInfo();
  int FI = MI.getOperand(FIOperandNum).getIndex();
  int64_t Offset = MFI.getObjectOffset(FI) + MFI.getStackSize() +
                   MI.getOperand(FIOperandNum + 1).getImm();
  unsigned Opcode;
  switch (MI.getOpcode()) {
  case Potados::LDfi:
    Opcode = Potados::LDsp;
    break;
  case Potados::STfi:
    Opcode = Potados::STsp;
    break;
  case Potados::LEAfi:
    Opcode = Potados::LEAsp;
    break;
  case Potados::LEAfiPrivate:
    Opcode = Potados::LEAspPrivate;
    break;
  default:
    report_fatal_error("unexpected POTADOS frame-index instruction");
  }
  MI.setDesc(MI.getMF()->getSubtarget().getInstrInfo()->get(Opcode));
  MI.getOperand(FIOperandNum).ChangeToImmediate(Offset);
  MI.removeOperand(FIOperandNum + 1);
  return false;
}
Register PotadosRegisterInfo::getFrameRegister(const MachineFunction &) const {
  return Potados::SP;
}
