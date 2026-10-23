// Machine instructions are expanded by the flat assembly printer. The project
// assembler owns binary encoding; this target intentionally emits no ELF objects.
class PInst<dag Outs, dag Ins, list<dag> Pat = []> : Instruction {
  let Namespace = "Potados";
  let Size = 2;
  let OutOperandList = Outs;
  let InOperandList = Ins;
  let Pattern = Pat;
  let isPseudo = 1;
  let isCodeGenOnly = 1;
  let hasSideEffects = 0;
  let mayLoad = 0;
  let mayStore = 0;
}
def SDT_PCall : SDTypeProfile<0, -1, [SDTCisVT<0, iPTR>]>;
def SDT_PBr : SDTypeProfile<0, 4, [SDTCisVT<0, i16>, SDTCisSameAs<0, 1>, SDTCisVT<2, OtherVT>, SDTCisVT<3, i16>]>;
def SDT_PSet : SDTypeProfile<1, 3, [SDTCisVT<0, i16>, SDTCisSameAs<1, 2>, SDTCisVT<1, i16>, SDTCisVT<3, i16>]>;
def SDT_PCallStart : SDCallSeqStart<[SDTCisVT<0, i16>, SDTCisVT<1, i16>]>;
def SDT_PCallEnd : SDCallSeqEnd<[SDTCisVT<0, i16>, SDTCisVT<1, i16>]>;
def pret : SDNode<"PotadosISD::RET", SDTNone, [SDNPHasChain, SDNPOptInGlue, SDNPVariadic]>;
def pcall : SDNode<"PotadosISD::CALL", SDT_PCall, [SDNPHasChain, SDNPOutGlue, SDNPOptInGlue, SDNPVariadic]>;
def pbr : SDNode<"PotadosISD::BR_CC", SDT_PBr, [SDNPHasChain]>;
def pset : SDNode<"PotadosISD::SETCC", SDT_PSet>;
// C addresses count 16-bit cells. Keep these opaque to the ordinary LLVM
// memory DAG, whose object offsets and alias sizes count eight-bit octets.
def SDT_PAddress : SDTypeProfile<1, 1, [SDTCisVT<0, i16>, SDTCisVT<1, i16>]>;
def SDT_PLoad : SDTypeProfile<1, 1, [SDTCisVT<0, i16>, SDTCisVT<1, i16>]>;
def SDT_PStore : SDTypeProfile<0, 2, [SDTCisVT<0, i16>, SDTCisVT<1, i16>]>;
def paddress : SDNode<"PotadosISD::ADDRESS", SDT_PAddress>;
def ploadword : SDNode<"PotadosISD::LOAD_WORD", SDT_PLoad,
                      [SDNPHasChain, SDNPMayLoad, SDNPMemOperand]>;
def pstoreword : SDNode<"PotadosISD::STORE_WORD", SDT_PStore,
                       [SDNPHasChain, SDNPMayStore, SDNPMemOperand]>;
def pcallstart : SDNode<"ISD::CALLSEQ_START", SDT_PCallStart, [SDNPHasChain, SDNPOutGlue]>;
def pcallend : SDNode<"ISD::CALLSEQ_END", SDT_PCallEnd, [SDNPHasChain, SDNPOptInGlue, SDNPOutGlue]>;
def brtarget : Operand<OtherVT>;
foreach Op = ["ADD", "SUB", "AND", "OR", "XOR"] in {
  def Op : PInst<(outs GPR:$dst), (ins GPR:$lhs, GPR:$rhs)>;
}
def : Pat<(add GPR:$a, GPR:$b), (ADD GPR:$a, GPR:$b)>;
def : Pat<(sub GPR:$a, GPR:$b), (SUB GPR:$a, GPR:$b)>;
def : Pat<(and GPR:$a, GPR:$b), (AND GPR:$a, GPR:$b)>;
def : Pat<(or GPR:$a, GPR:$b), (OR GPR:$a, GPR:$b)>;
def : Pat<(xor GPR:$a, GPR:$b), (XOR GPR:$a, GPR:$b)>;
def MOV : PInst<(outs ALL:$dst), (ins ALL:$src)> { let isAsCheapAsAMove = 1; }
def LI : PInst<(outs GPR:$dst), (ins i16imm:$imm), [(set GPR:$dst, imm:$imm)]> { let isReMaterializable = 1; }
def LIga : PInst<(outs GPR:$dst), (ins i16imm:$symbol)> { let isReMaterializable = 1; }
def : Pat<(i16 tglobaladdr:$symbol), (LIga tglobaladdr:$symbol)>;
def : Pat<(i16 texternalsym:$symbol), (LIga texternalsym:$symbol)>;
def MUL8 : PInst<(outs GPR:$dst), (ins GPR:$lhs, GPR:$rhs)>;
let Defs = [R6], Uses = [SP],
    Constraints = "@earlyclobber $dst" in
  def MUL16 : PInst<(outs GPR:$dst), (ins GPR:$lhs, GPR:$rhs), [(set GPR:$dst, (mul GPR:$lhs, GPR:$rhs))]>;
foreach Op = ["SHLi", "SRLi", "SRAi"] in {
  def Op : PInst<(outs GPR:$dst), (ins GPR:$src, i16imm:$amount)>;
}
let Constraints = "$dst = $src" in {
  def SHLr : PInst<(outs GPR:$dst), (ins GPR:$src, GPR:$amount), [(set GPR:$dst, (shl GPR:$src, GPR:$amount))]> { let Defs = [R6]; }
  def SRLr : PInst<(outs GPR:$dst), (ins GPR:$src, GPR:$amount), [(set GPR:$dst, (srl GPR:$src, GPR:$amount))]>;
  def SRAr : PInst<(outs GPR:$dst), (ins GPR:$src, GPR:$amount), [(set GPR:$dst, (sra GPR:$src, GPR:$amount))]>;
}
let mayLoad = 1, Defs = [R6] in {
  def LD16 : PInst<(outs GPR:$dst), (ins GPR:$ptr)>;
  def LDprivate : PInst<(outs GPR:$dst), (ins GPR:$ptr)>;
  def LDfi : PInst<(outs ALL:$dst), (ins i16imm:$fi, i16imm:$offset)>;
  def LDsp : PInst<(outs ALL:$dst), (ins i16imm:$offset)> { let Uses = [SP]; }
}
let mayStore = 1, Defs = [R6] in {
  def ST16 : PInst<(outs), (ins GPR:$src, GPR:$ptr)>;
  def STprivate : PInst<(outs), (ins GPR:$src, GPR:$ptr)>;
  def STfi : PInst<(outs), (ins ALL:$src, i16imm:$fi, i16imm:$offset)>;
  def STsp : PInst<(outs), (ins ALL:$src, i16imm:$offset)> { let Uses = [SP]; }
}
let Uses = [SP] in {
  def LEAfi : PInst<(outs GPR:$dst), (ins i16imm:$fi, i16imm:$offset)>;
  def LEAsp : PInst<(outs GPR:$dst), (ins i16imm:$offset)> { let Defs = [R6]; }
  def LEAfiPrivate : PInst<(outs GPR:$dst), (ins i16imm:$fi, i16imm:$offset)>;
  def LEAspPrivate : PInst<(outs GPR:$dst), (ins i16imm:$offset)> { let Defs = [R6]; }
}
let Uses = [SP], Defs = [SP, R6] in
  def ADJSP : PInst<(outs), (ins i16imm:$amount)>;
let isBranch = 1, isTerminator = 1 in {
  def BR : PInst<(outs), (ins brtarget:$target), [(br bb:$target)]> { let isBarrier = 1; }
  def BRCC : PInst<(outs), (ins GPR:$lhs, GPR:$rhs, brtarget:$target, i16imm:$cc), [(pbr GPR:$lhs, GPR:$rhs, bb:$target, imm:$cc)]>;
}
def SETCC : PInst<(outs GPR:$dst), (ins GPR:$lhs, GPR:$rhs, i16imm:$cc), [(set GPR:$dst, (pset GPR:$lhs, GPR:$rhs, imm:$cc))]>;
let Constraints = "$dst = $false", isSelect = 1 in
  def SELECT : PInst<(outs GPR:$dst), (ins GPR:$cond, GPR:$true, GPR:$false), [(set GPR:$dst, (select GPR:$cond, GPR:$true, GPR:$false))]>;
let isCall = 1, Defs = [R2, R3, R4, R5, R6, R7], Uses = [SP] in {
  def CALLg : PInst<(outs), (ins i16imm:$callee, variable_ops)>;
  def CALLr : PInst<(outs), (ins ALL:$callee, variable_ops)>;
}
def : Pat<(pcall (i16 tglobaladdr:$callee)), (CALLg tglobaladdr:$callee)>;
def : Pat<(pcall (i16 texternalsym:$callee)), (CALLg texternalsym:$callee)>;
def : Pat<(pcall ALL:$callee), (CALLr ALL:$callee)>;
let isReturn = 1, isTerminator = 1, isBarrier = 1, Uses = [R7] in
  def RET : PInst<(outs), (ins), [(pret)]>;
let hasSideEffects = 1, Defs = [SP], Uses = [SP] in {
  def ADJCALLSTACKDOWN : PInst<(outs), (ins i16imm:$a, i16imm:$b), [(pcallstart timm:$a, timm:$b)]>;
  def ADJCALLSTACKUP : PInst<(outs), (ins i16imm:$a, i16imm:$b), [(pcallend timm:$a, timm:$b)]>;
}
