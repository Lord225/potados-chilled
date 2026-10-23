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
bool PotadosInstrInfo::analyzeBranch(MachineBasicBlock &MBB,
                                     MachineBasicBlock *&TBB,
                                     MachineBasicBlock *&FBB,
                                     SmallVectorImpl<MachineOperand> &Cond,
                                     bool) const {
  TBB = FBB = nullptr;
  Cond.clear();
  for (auto I = MBB.getFirstTerminator(), E = MBB.end(); I != E; ++I) {
    if (I->isDebugInstr())
      continue;
    if (I->getOpcode() == Potados::BRCC && !TBB) {
      TBB = I->getOperand(2).getMBB();
      Cond.push_back(I->getOperand(0));
      Cond.push_back(I->getOperand(1));
      Cond.push_back(I->getOperand(3));
    } else if (I->getOpcode() == Potados::BR && !FBB) {
      if (!TBB)
        TBB = I->getOperand(0).getMBB();
      else if (!Cond.empty())
        FBB = I->getOperand(0).getMBB();
      else
        return true;
    } else {
      return true;
    }
  }
  return false;
}
unsigned PotadosInstrInfo::removeBranch(MachineBasicBlock &MBB,
                                        int *BytesRemoved) const {
  unsigned Count = 0;
  if (BytesRemoved)
    *BytesRemoved = 0;
  auto I = MBB.end();
  while (I != MBB.begin()) {
    --I;
    if (I->isDebugInstr())
      continue;
    if (I->getOpcode() != Potados::BR && I->getOpcode() != Potados::BRCC)
      break;
    if (BytesRemoved)
      *BytesRemoved += getInstSizeInBytes(*I);
    I = MBB.erase(I);
    ++Count;
  }
  return Count;
}
unsigned PotadosInstrInfo::insertBranch(
    MachineBasicBlock &MBB, MachineBasicBlock *TBB, MachineBasicBlock *FBB,
    ArrayRef<MachineOperand> Cond, const DebugLoc &DL, int *BytesAdded) const {
  if (!TBB || (Cond.size() != 0 && Cond.size() != 3) || (Cond.empty() && FBB))
    report_fatal_error("invalid POTADOS branch insertion");
  unsigned Count = 1;
  if (Cond.empty()) {
    BuildMI(&MBB, DL, get(Potados::BR)).addMBB(TBB);
  } else {
    BuildMI(&MBB, DL, get(Potados::BRCC))
        .add(Cond[0])
        .add(Cond[1])
        .addMBB(TBB)
        .add(Cond[2]);
    if (FBB) {
      BuildMI(&MBB, DL, get(Potados::BR)).addMBB(FBB);
      ++Count;
    }
  }
  if (BytesAdded)
    *BytesAdded = Count * 2;
  return Count;
}
bool PotadosInstrInfo::reverseBranchCondition(
    SmallVectorImpl<MachineOperand> &Cond) const {
  if (Cond.size() != 3 || !Cond[2].isImm())
    return true;
  Cond[2].setImm(ISD::getSetCCInverse(
      static_cast<ISD::CondCode>(Cond[2].getImm()), MVT::i16));
  return false;
}
