class PotadosReg<bits<3> Enc, string Name> : Register<Name> {
  let Namespace = "Potados";
  let HWEncoding{2-0} = Enc;
  let DwarfNumbers = [Enc];
}
def ZERO : PotadosReg<0, "ZERO">;
def SP : PotadosReg<1, "SP">;
def R2 : PotadosReg<2, "R2">;
def R3 : PotadosReg<3, "R3">;
def R4 : PotadosReg<4, "R4">;
def R5 : PotadosReg<5, "R5">;
def R6 : PotadosReg<6, "R6">;
def R7 : PotadosReg<7, "R7">;
def GPR : RegisterClass<"Potados", [i16], 16, (add R2, R3, R4, R5)>;
def ALL : RegisterClass<"Potados", [i16], 16, (add ZERO, SP, R2, R3, R4, R5, R6, R7)>;
