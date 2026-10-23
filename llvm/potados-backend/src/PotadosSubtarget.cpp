#include "PotadosSubtarget.h"
#include "llvm/CodeGen/LibcallLoweringInfo.h"

using namespace llvm;

#define DEBUG_TYPE "potados-subtarget"

#define GET_SUBTARGETINFO_TARGET_DESC
#define GET_SUBTARGETINFO_CTOR
#include "PotadosGenSubtargetInfo.inc"

PotadosSubtarget::PotadosSubtarget(const Triple &TT, StringRef CPU,
                                   StringRef FS, const TargetMachine &TM)
    : PotadosGenSubtargetInfo(TT, CPU.empty() ? "generic" : CPU,
                              CPU.empty() ? "generic" : CPU, FS),
      InstrInfo(*this), TLInfo(TM, *this), FrameLowering() {
  ParseSubtargetFeatures(CPU.empty() ? "generic" : CPU,
                         CPU.empty() ? "generic" : CPU, FS);
}

void PotadosSubtarget::initLibcallLoweringInfo(
    LibcallLoweringInfo &Info) const {
  Info.setLibcallImpl(RTLIB::MUL_I16, RTLIB::impl___mulhi3);
  Info.setLibcallImpl(RTLIB::MUL_I32, RTLIB::Unsupported);
  Info.setLibcallImpl(RTLIB::MUL_I64, RTLIB::Unsupported);
  Info.setLibcallImpl(RTLIB::SDIV_I16, RTLIB::impl___divhi3);
  Info.setLibcallImpl(RTLIB::UDIV_I16, RTLIB::impl___udivhi3);
  Info.setLibcallImpl(RTLIB::SREM_I16, RTLIB::impl___modhi3);
  Info.setLibcallImpl(RTLIB::UREM_I16, RTLIB::impl___umodhi3);
  Info.setLibcallImpl(RTLIB::SDIV_I32, RTLIB::impl___divsi3);
  Info.setLibcallImpl(RTLIB::UDIV_I32, RTLIB::impl___udivsi3);
  Info.setLibcallImpl(RTLIB::SREM_I32, RTLIB::impl___modsi3);
  Info.setLibcallImpl(RTLIB::UREM_I32, RTLIB::impl___umodsi3);
  Info.setLibcallImpl(RTLIB::SDIV_I64, RTLIB::impl___divdi3);
  Info.setLibcallImpl(RTLIB::UDIV_I64, RTLIB::impl___udivdi3);
  Info.setLibcallImpl(RTLIB::SREM_I64, RTLIB::impl___moddi3);
  Info.setLibcallImpl(RTLIB::UREM_I64, RTLIB::impl___umoddi3);
}
