cmake_minimum_required(VERSION 3.13)

# Requires the Raspberry Pi Pico SDK: export PICO_SDK_PATH=/path/to/pico-sdk
include($ENV{PICO_SDK_PATH}/external/pico_sdk_import.cmake)

project(bench_capture C CXX ASM)
set(CMAKE_C_STANDARD 11)

pico_sdk_init()

add_executable(bench_capture main.c)
target_compile_options(bench_capture PRIVATE -Wall -Wextra -Wno-unused-parameter)
target_link_libraries(bench_capture pico_stdlib hardware_adc hardware_dma hardware_irq hardware_sync)

pico_enable_stdio_usb(bench_capture 1)
pico_enable_stdio_uart(bench_capture 0)
pico_add_extra_outputs(bench_capture)
