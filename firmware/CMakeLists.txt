cmake_minimum_required(VERSION 3.13)

# Requires the Raspberry Pi Pico SDK: export PICO_SDK_PATH=/path/to/pico-sdk
include($ENV{PICO_SDK_PATH}/external/pico_sdk_import.cmake)

project(f2a_timer C CXX ASM)
set(CMAKE_C_STANDARD 11)

pico_sdk_init()

add_executable(f2a_timer main.c)
target_compile_options(f2a_timer PRIVATE -Wall -Wextra -Wno-unused-parameter)
target_link_libraries(f2a_timer pico_stdlib hardware_gpio hardware_irq hardware_sync)

pico_enable_stdio_usb(f2a_timer 1)
pico_enable_stdio_uart(f2a_timer 0)
pico_add_extra_outputs(f2a_timer)
