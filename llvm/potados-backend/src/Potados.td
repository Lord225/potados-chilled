include "llvm/Target/Target.td"
include "PotadosRegisterInfo.td"
include "PotadosInstrInfo.td"
defm : RemapAllTargetPseudoPointerOperands<GPR>;
def : Processor<"generic", NoItineraries, []>;
def PotadosInstrInfo : InstrInfo;
def Potados : Target { let InstructionSet = PotadosInstrInfo; }
