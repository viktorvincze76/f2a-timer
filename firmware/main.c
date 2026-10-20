/*
 * F2A timer - sensor interface firmware (Raspberry Pi Pico, RP2040/RP2350)
 *
 * Timestamps sensor edges in a high-priority interrupt against the 64-bit
 * microsecond hardware timer and streams them to the host over USB serial.
 *
 * This is what removes the old system's weakness: the timestamp is fixed the
 * moment the edge arrives, so however late the host OS gets round to reading
 * it, the measured lap times are unaffected.
 *
 * Protocol (one ASCII line per message, see docs/protocol.md):
 *   device -> host   HELLO f2a-timer <version>
 *                    E <seq> <channel S|H> <active 1|0> <t_us>
 *                    B <t_us> <dropped>              heartbeat, once a second
 *   host -> device   ?                               re-send HELLO
 *                    T <period_ms> <width_us>        start test pulses
 *                    T 0                             stop test pulses
 */
#include <stdio.h>
#include "pico/stdlib.h"
#include "pico/stdio_usb.h"
#include "hardware/gpio.h"
#include "hardware/irq.h"
#include "hardware/sync.h"
#include "hardware/structs/timer.h"

#define FW_VERSION "0.1.0"

#define PIN_SENSOR         2   // sensor pulse, via 3.3 V Schmitt buffer (see docs/hardware.md)
#define PIN_HANDLE         3   // handle-in-pylon switch to GND, internal pull-up
#define PIN_TEST_OUT       15  // test pulse output; jumper to PIN_SENSOR for loopback
#define SENSOR_ACTIVE_HIGH 1   // set to 0 if the sensor pulls its output low on a pass

#define HANDLE_DEBOUNCE_US 20000
#define HEARTBEAT_US       1000000
#define LED_ON_US          50000

#define QUEUE_LEN 1024         // must be a power of two

typedef struct {
    uint64_t t_us;
    uint32_t seq;
    char ch;
    bool active;
} event_t;

// Single consumer (main loop). Producers are the sensor ISR and the main
// loop's handle debouncer; the latter disables interrupts while pushing.
static event_t queue[QUEUE_LEN];
static volatile uint32_t q_head, q_tail;
static volatile uint32_t q_dropped;
static uint32_t next_seq;

// 64-bit timer read that is safe in an ISR and runs from RAM.
static inline uint64_t now_us(void) {
    uint32_t hi = timer_hw->timerawh, lo, hi2;
    for (;;) {
        lo = timer_hw->timerawl;
        hi2 = timer_hw->timerawh;
        if (hi == hi2) break;
        hi = hi2;
    }
    return ((uint64_t)hi << 32) | lo;
}

// Sequence numbers are assigned even to dropped events, so the host sees a gap.
static inline void queue_push(uint64_t t, char ch, bool active) {
    uint32_t seq = next_seq++;
    uint32_t h = q_head;
    if (h - q_tail >= QUEUE_LEN) {
        q_dropped++;
        return;
    }
    queue[h & (QUEUE_LEN - 1)] = (event_t){t, seq, ch, active};
    __dmb();
    q_head = h + 1;
}

// Kept in RAM so a flash cache miss can never delay the timestamp.
static void __not_in_flash_func(sensor_isr)(void) {
    uint64_t t = now_us();  // first thing: everything after this is latency-free
    uint32_t ev = gpio_get_irq_event_mask(PIN_SENSOR);
    if (!ev) return;
    gpio_acknowledge_irq(PIN_SENSOR, ev);

    bool rise = ev & GPIO_IRQ_EDGE_RISE;
    bool fall = ev & GPIO_IRQ_EDGE_FALL;
    if (rise && fall) {
        // Pulse shorter than the ISR latency: both edges latched. The current
        // pin level tells which came last.
        bool last_rise = gpio_get(PIN_SENSOR);
        queue_push(t, 'S', last_rise ? !SENSOR_ACTIVE_HIGH : SENSOR_ACTIVE_HIGH);
        queue_push(t, 'S', last_rise ? SENSOR_ACTIVE_HIGH : !SENSOR_ACTIVE_HIGH);
    } else {
        queue_push(t, 'S', rise == SENSOR_ACTIVE_HIGH);
    }
}

// ---- test pulse generator -------------------------------------------------

static repeating_timer_t test_timer;
static bool test_running;
static uint32_t test_width_us;

static int64_t test_pulse_end(alarm_id_t id, void *user) {
    gpio_put(PIN_TEST_OUT, !SENSOR_ACTIVE_HIGH);
    return 0;
}

static bool test_pulse_start(repeating_timer_t *rt) {
    gpio_put(PIN_TEST_OUT, SENSOR_ACTIVE_HIGH);
    add_alarm_in_us(test_width_us, test_pulse_end, NULL, true);
    return true;
}

static void set_test_pulses(uint32_t period_ms, uint32_t width_us) {
    if (test_running) {
        cancel_repeating_timer(&test_timer);
        test_running = false;
    }
    gpio_put(PIN_TEST_OUT, !SENSOR_ACTIVE_HIGH);
    if (period_ms == 0) return;
    test_width_us = width_us ? width_us : 2000;
    test_running = add_repeating_timer_ms(-(int32_t)period_ms, test_pulse_start, NULL, &test_timer);
}

// ---- host commands --------------------------------------------------------

static void say_hello(void) {
    printf("HELLO f2a-timer %s\n", FW_VERSION);
}

static void handle_command(const char *line) {
    unsigned period_ms = 0, width_us = 0;
    if (line[0] == '?') {
        say_hello();
    } else if (sscanf(line, "T %u %u", &period_ms, &width_us) >= 1) {
        set_test_pulses(period_ms, width_us);
    }
}

static void poll_commands(void) {
    static char buf[64];
    static size_t len;
    int c;
    while ((c = getchar_timeout_us(0)) != PICO_ERROR_TIMEOUT) {
        if (c == '\n' || c == '\r') {
            if (len) {
                buf[len] = '\0';
                handle_command(buf);
                len = 0;
            }
        } else if (len < sizeof buf - 1) {
            buf[len++] = (char)c;
        }
    }
}

// ---- main -----------------------------------------------------------------

int main(void) {
    stdio_init_all();

    gpio_init(PIN_SENSOR);
    gpio_set_dir(PIN_SENSOR, GPIO_IN);
    gpio_disable_pulls(PIN_SENSOR);

    gpio_init(PIN_HANDLE);
    gpio_set_dir(PIN_HANDLE, GPIO_IN);
    gpio_pull_up(PIN_HANDLE);

    gpio_init(PIN_TEST_OUT);
    gpio_set_dir(PIN_TEST_OUT, GPIO_OUT);
    gpio_put(PIN_TEST_OUT, !SENSOR_ACTIVE_HIGH);

#ifdef PICO_DEFAULT_LED_PIN
    gpio_init(PICO_DEFAULT_LED_PIN);
    gpio_set_dir(PICO_DEFAULT_LED_PIN, GPIO_OUT);
#endif

    gpio_add_raw_irq_handler(PIN_SENSOR, sensor_isr);
    gpio_set_irq_enabled(PIN_SENSOR, GPIO_IRQ_EDGE_RISE | GPIO_IRQ_EDGE_FALL, true);
    irq_set_priority(IO_IRQ_BANK0, PICO_HIGHEST_IRQ_PRIORITY);  // pre-empts USB and alarms
    irq_set_enabled(IO_IRQ_BANK0, true);

    // The handle switch only needs millisecond resolution, so it is polled and
    // debounced here. The event carries the time of the first change.
    bool handle_stable = !gpio_get(PIN_HANDLE);
    bool handle_candidate = handle_stable;
    uint64_t handle_changed_at = 0;

    bool was_connected = false;
    uint64_t next_heartbeat = now_us() + HEARTBEAT_US;
    uint64_t led_off_at = 0;

    for (;;) {
        uint64_t now = now_us();

        bool raw = !gpio_get(PIN_HANDLE);
        if (raw != handle_candidate) {
            handle_candidate = raw;
            handle_changed_at = now;
        } else if (raw != handle_stable && now - handle_changed_at >= HANDLE_DEBOUNCE_US) {
            handle_stable = raw;
            uint32_t irq_state = save_and_disable_interrupts();
            queue_push(handle_changed_at, 'H', handle_stable);
            restore_interrupts(irq_state);
        }

        bool connected = stdio_usb_connected();
        if (connected && !was_connected) say_hello();
        was_connected = connected;

        if (connected) {
            poll_commands();
            while (q_tail != q_head) {
                event_t e = queue[q_tail & (QUEUE_LEN - 1)];
                __dmb();
                q_tail = q_tail + 1;
                printf("E %lu %c %d %llu\n", (unsigned long)e.seq, e.ch, e.active,
                       (unsigned long long)e.t_us);
                if (e.ch == 'S' && e.active) led_off_at = now + LED_ON_US;
            }
            if (now >= next_heartbeat) {
                printf("B %llu %lu\n", (unsigned long long)now, (unsigned long)q_dropped);
                next_heartbeat += HEARTBEAT_US;
            }
        }
        // Events queue up while no host is connected and are sent on reconnect.

#ifdef PICO_DEFAULT_LED_PIN
        gpio_put(PICO_DEFAULT_LED_PIN, now < led_off_at);
#endif
    }
}
