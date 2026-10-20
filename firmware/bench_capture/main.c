/*
 * Bench-test capture firmware (Raspberry Pi Pico 2 / Pico)
 *
 * Samples the two front-end outputs (ADC0 = DC light level, ADC1 = AC signal)
 * round-robin at 256 kSps in total via DMA, sums blocks of 16 samples per
 * channel (oversampling, ~2 extra bits) and streams 8000 sample pairs per
 * second to the host over USB serial.
 *
 * Output, one line per message:
 *   <dc_sum> <ac_sum>                 a sample pair, each the sum of 16 12-bit readings
 *   M <index>                         mark button pressed at sample <index>
 *   # <index> <overruns>              once a second; <index> = pairs sent so far
 * Sample <index> counts from 0 at power-up. Its time is index / 8000 s, derived
 * from the ADC clock, so the host never needs its own timestamps.
 */
#include <stdio.h>
#include "pico/stdlib.h"
#include "pico/stdio_usb.h"
#include "hardware/adc.h"
#include "hardware/dma.h"
#include "hardware/irq.h"
#include "hardware/sync.h"

#define PIN_MARK      15
#define PIN_PSU_MODE  23        // high = PWM mode, less ripple on 3.3 V

#define ADC_TOTAL_SPS 256000    // both channels together
#define OVERSAMPLE    16        // readings summed per output sample, per channel
#define BLOCK         512       // DMA block, in readings (even, multiple of 2*OVERSAMPLE)

static uint16_t buf[2][BLOCK];
static int dma_chan[2];
static volatile uint32_t ready;       // bit i set: buf[i] is full and unprocessed
static volatile uint32_t overruns;    // blocks overwritten before being processed

static void dma_isr(void) {
    for (int i = 0; i < 2; i++) {
        uint32_t mask = 1u << dma_chan[i];
        if (dma_hw->ints0 & mask) {
            dma_hw->ints0 = mask;
            if (ready & (1u << i)) overruns++;
            ready |= 1u << i;
            dma_channel_set_write_addr(dma_chan[i], buf[i], false);  // re-arm for the next lap
        }
    }
}

static void start_sampling(void) {
    adc_init();
    adc_gpio_init(26);
    adc_gpio_init(27);
    adc_select_input(0);
    adc_set_round_robin(0b11);  // ADC0, ADC1, ADC0, ...: even entries DC, odd entries AC
    adc_fifo_setup(true, true, 1, false, false);
    adc_set_clkdiv(48000000.0f / ADC_TOTAL_SPS - 1.0f);

    for (int i = 0; i < 2; i++) dma_chan[i] = dma_claim_unused_channel(true);
    for (int i = 0; i < 2; i++) {
        dma_channel_config c = dma_channel_get_default_config(dma_chan[i]);
        channel_config_set_transfer_data_size(&c, DMA_SIZE_16);
        channel_config_set_read_increment(&c, false);
        channel_config_set_write_increment(&c, true);
        channel_config_set_dreq(&c, DREQ_ADC);
        channel_config_set_chain_to(&c, dma_chan[!i]);  // ping-pong, no gaps
        dma_channel_configure(dma_chan[i], &c, buf[i], &adc_hw->fifo, BLOCK, false);
        dma_channel_set_irq0_enabled(dma_chan[i], true);
    }
    irq_set_exclusive_handler(DMA_IRQ_0, dma_isr);
    irq_set_enabled(DMA_IRQ_0, true);

    dma_channel_start(dma_chan[0]);
    adc_run(true);
}

int main(void) {
    stdio_init_all();

    gpio_init(PIN_PSU_MODE);
    gpio_set_dir(PIN_PSU_MODE, GPIO_OUT);
    gpio_put(PIN_PSU_MODE, 1);

    gpio_init(PIN_MARK);
    gpio_set_dir(PIN_MARK, GPIO_IN);
    gpio_pull_up(PIN_MARK);

    start_sampling();

    uint64_t index = 0;
    uint64_t next_status = 8000;
    int next_buf = 0;
    bool mark_was_down = false;
    uint64_t mark_ignore_until = 0;

    for (;;) {
        if (!(ready & (1u << next_buf))) {
            tight_loop_contents();
            continue;
        }
        bool connected = stdio_usb_connected();
        const uint16_t *b = buf[next_buf];
        for (int k = 0; k < BLOCK; k += 2 * OVERSAMPLE) {
            uint32_t dc = 0, ac = 0;
            for (int j = 0; j < 2 * OVERSAMPLE; j += 2) {
                dc += b[k + j];
                ac += b[k + j + 1];
            }
            if (connected) printf("%lu %lu\n", (unsigned long)dc, (unsigned long)ac);
            index++;
        }
        uint32_t irq_state = save_and_disable_interrupts();  // the ISR may set the other bit
        ready &= ~(1u << next_buf);
        restore_interrupts(irq_state);
        next_buf ^= 1;

        bool mark_down = !gpio_get(PIN_MARK);
        if (mark_down && !mark_was_down && index >= mark_ignore_until) {
            if (connected) printf("M %llu\n", (unsigned long long)index);
            mark_ignore_until = index + 2000;  // 250 ms debounce
        }
        mark_was_down = mark_down;

        if (index >= next_status) {
            if (connected) printf("# %llu %lu\n", (unsigned long long)index, (unsigned long)overruns);
            next_status += 8000;
        }
    }
}
