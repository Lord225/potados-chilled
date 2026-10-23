cmake_minimum_required(VERSION 3.20)

project(Potados LANGUAGES C CXX)

find_package(LLVM 23 REQUIRED CONFIG)
if(NOT LLVM_PACKAGE_VERSION MATCHES "^23\\.")
  message(FATAL_ERROR "The backend requires LLVM 23 at the pinned revision")
endif()

list(APPEND CMAKE_MODULE_PATH "${LLVM_CMAKE_DIR}")
include(AddLLVM)
include(TableGen)

if(NOT LLVM_TABLEGEN_EXE)
  set(LLVM_TABLEGEN_EXE "${LLVM_TOOLS_BINARY_DIR}/llvm-tblgen")
  set(LLVM_TABLEGEN_TARGET "${LLVM_TABLEGEN_EXE}")
endif()

include_directories(SYSTEM ${LLVM_INCLUDE_DIRS})
include_directories(${CMAKE_CURRENT_SOURCE_DIR}/src)
include_directories(${CMAKE_CURRENT_BINARY_DIR})
add_definitions(${LLVM_DEFINITIONS})

set(CMAKE_CXX_STANDARD 17 CACHE STRING "C++ standard")
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

set(LLVM_TARGET_DEFINITIONS src/Potados.td)
tablegen(LLVM PotadosGenAsmWriter.inc -gen-asm-writer)
tablegen(LLVM PotadosGenDAGISel.inc -gen-dag-isel)
tablegen(LLVM PotadosGenInstrInfo.inc -gen-instr-info)
tablegen(LLVM PotadosGenRegisterInfo.inc -gen-register-info)
tablegen(LLVM PotadosGenSDNodeInfo.inc -gen-sd-node-info)
tablegen(LLVM PotadosGenSubtargetInfo.inc -gen-subtarget)
add_public_tablegen_target(PotadosCommonTableGen)

add_llvm_library(Potados MODULE BUILDTREE_ONLY
  src/Potados.cpp
  src/PotadosAsmPrinter.cpp
  src/PotadosFrameLowering.cpp
  src/PotadosISelDAGToDAG.cpp
  src/PotadosISelLowering.cpp
  src/PotadosInstrInfo.cpp
  src/PotadosMC.cpp
  src/PotadosRegisterInfo.cpp
  src/PotadosSelectionDAGInfo.cpp
  src/PotadosSubtarget.cpp
  src/PotadosTargetMachine.cpp
  DEPENDS
  PotadosCommonTableGen
)

if(APPLE)
  target_link_options(Potados PRIVATE LINKER:-undefined,dynamic_lookup)
endif()

set_target_properties(Potados PROPERTIES PREFIX "")
