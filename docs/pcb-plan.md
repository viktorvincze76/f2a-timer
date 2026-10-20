# PCB plan: final system (rev A)

Status: **plan, before schematic capture.** Component values marked ⚑ are set after the bench test
([bench-test.md](bench-test.md)). Part availability was checked on 2026-10-20.

## 1. System

```
 ┌──────────── SENSOR HEAD  (board SH-1, inside the slit enclosure) ────────────┐
 │                                                                              │
 │  slit ─► D1 BPW21R ─► TIA ─┬─► DC ─┐                                          │
 │         (D2 optional)       └─► AC ─┤ ADS131M04  SPI  ┌──────────────┐        │
 │                                     │ 24-bit, 4 ch ◄──┤ Pico 2       │        │
 │                    LP5907 3.3 V ───►│ 7.3 kSps        │ (RP2350)     │        │
 │                    (analog)         └── CLKIN 7.5 MHz ┤ detection,   │ USB    │
 │  SCL3300 inclinometer ─────────────────────── SPI ───►│ timestamps   ├─► (service /
 │  status + level LEDs ◄────────────────────────────────┤              │    bench mode)
 │                                                        └──────┬───────┘        │
 │  RJ45 ─► PTC ─► reverse-polarity diode ─► TVS ─► AP63205 buck ─► 5 V           │
 │     └─────────── RS-485 (THVD1450 + SM712) ◄── UART 1 Mbaud ──┘               │
 └──────┬───────────────────────────────────────────────────────────────────────┘
        │ 76 m outdoor Cat5e: data on one pair, 12 V on two pairs
 ┌──────┴──────────── BASE STATION  (board BS-1) ───────────────────────────────┐
 │  RJ45 ◄─ PTC ◄─ OR ◄─┬─ 12 V field battery (DC jack)                         │
 │                      └─ TPS61085 boost 5 → 12 V (from the laptop's USB)      │
 │  RS-485 (THVD1450 + SM712) ◄──► Pico 2 ──USB──► Linux PC (Python app)         │
 │  handle switch (3.5 mm jack) ──► Pico 2 ──► buzzer, LEDs; GPS header (option)│
 └──────────────────────────────────────────────────────────────────────────────┘
```

**Design rules**
- The sensor head timestamps every pass itself. Its ADC clock is derived from the Pico's crystal, so a sample index *is* a timestamp.
- Both boards use a **Raspberry Pi Pico 2 module**, soldered on through its castellated edge, rather than a bare RP2350. That saves the crystal, flash, USB and regulator design, is easy for the club to solder and replace, and keeps one toolchain.
- The analog front end is the **same circuit topology as the bench test**, so bench measurements carry over directly.
- Only parts in stock at two or more distributors are used.

### Cable (Cat5e, T568B pin-out; this is **not Ethernet**, so label both ends)

| RJ45 pins | Pair | Signal |
|---|---|---|
| 1, 2 | orange | RS-485 A, B |
| 3, 6 | green | reserved (2nd RS-485 / sync); TVS-protected, not connected |
| 4, 5 | blue | +12 V (9–18 V) |
| 7, 8 | brown | GND |

Voltage drop: 76 m × 2 conductors per pole, about 6.4 Ω loop resistance × 70 mA ≈ 0.45 V. That is negligible.

## 2. Board SH-1: sensor head

**Board:** 4 layers (signal, solid GND, power, signal), about 100 × 65 mm, **black solder mask**
(it sits under the optical chamber), 4 × M3 holes. It mounts horizontally on the enclosure floor.
The photodiode goes through a hole in a black 3D-printed baffle that separates the optical chamber from the electronics.

| Block | Parts | Notes |
|---|---|---|
| Input protection | F1 MF-MSMF020-2 PTC 200 mA · D3 B240A reverse-polarity Schottky · D4 SMBJ18A TVS · C 22 µF/35 V | Survives reversed, shorted or 24 V connections |
| 5 V | U5 **AP63205WU-7** buck (3.8–32 V in), L 4.7 µH (datasheet value), 2 × 22 µF out, ferrite bead + 10 µF filter | About 70 mA load; keep it at the far end from the analog section |
| 3.3 V analog | U4 **LP5907MFX-3.3** ultra-low-noise LDO (6.5 µV rms) from the filtered 5 V | AVDD for the ADC and op-amps |
| Detector | D1 **BPW21R** (TO-5, leads bent ~60° so it looks 30° up). **D2 optional**: footprint 10 mm to the side | D2 sees a second field ~4° away: direction, redundancy, cloud cancellation |
| Front end, per diode | U1/U2 **MCP6022** dual op-amp: A = TIA (Rf ⚑ 270 kΩ 0.1 %, Cf 33 pF C0G), B = AC stage (gain ⚑ ×10, HP 1 Hz, LP 1.6 kHz) | As on the bench, but scaled to the ADC's ±1.2 V range |
| References | Vb ≈ 50 mV and Vmid ≈ 1.2 V from AVDD by divider + 10 µF | ADC inputs are differential: DC = TIA − Vb, AC = stage − Vmid |
| ADC | U3 **ADS131M04IPWR** (TSSOP-20), internal 1.2 V reference, 4 channels: D1-DC, D1-AC, D2-DC, D2-AC; RC 100 Ω/10 nF C0G per input | CLKIN 7.5 MHz from the Pico (clk_sys/20 on GPOUT0 = GP21); OSR 512 → 7.3 kSps; the firmware sets the AC PGA (1–32) from the sky level |
| MCU | **Raspberry Pi Pico 2** module; VSYS from 5 V through a Schottky diode | USB stays accessible for firmware updates and stand-alone bench mode |
| Inclinometer | U6 **Murata SCL3300-D01** (SPI), centred on the board | Roll/pitch to ~0.01° resolution. Field procedure: read, turn the head 180°, read again; this cancels the sensor's offset |
| RS-485 | U7 **THVD1450DR** (±18 kV IEC ESD) · D5/D6 **SM712-02HTG** on both pairs · 120 Ω termination (solder jumper) | 1 Mbaud half duplex; the THVD1450 has built-in idle-bus fail-safe |
| Connector | J1 **Amphenol RJHSE-5380** shielded RJ45 (right angle, rear edge) | Behind an IP67 RJ45 feed-through or a rubber boot in the enclosure |
| User interface | Rear edge, side-looking LEDs: power (green), pass (red), level ◀ ● ▶ (yellow/green/yellow) · service button | Like Göran's red pass lamp, plus a levelling aid that works without the laptop |
| Monitoring | VIN and 5 V dividers into Pico ADC GP26/GP28 | Logged with every flight |

**Proposed Pico 2 pin map (sensor head):** GP0/GP1 UART0 TX/RX → RS-485, GP8 DE/RE · GP2–GP5 SPI0 SCK/MOSI/MISO/CS → ADC,
GP6 DRDY, GP7 ADC SYNC/RESET, GP21 CLKIN · GP10–GP13 SPI1 → SCL3300 · GP14 pass LED, GP15 status LED,
GP16–GP18 level LEDs, GP19 button · GP26 VIN monitor, GP28 5 V monitor.

**Layout rules**
1. Analog zone (D1/D2, U1/U2, U3 analog side, U4) at the front, under the slit. Power input and the buck at the rear corner. The Pico and digital parts lie in between.
2. Solid ground plane, not split. The ADS131M04's AGND and DGND join under the chip.
3. TIA input node: shortest possible trace, guard ring at Vb around pin 2, **no solder mask over the guard**, no other copper under it.
4. Buck loop as small as possible; nothing analog over its inductor's field.
5. CLKIN trace short, with a 33 Ω series resistor at the Pico. No SPI or clock traces near the TIA.

## 3. Board BS-1: base station

**Board:** 2 layers, about 80 × 60 mm, in a small ABS box next to the laptop.

| Block | Parts | Notes |
|---|---|---|
| 12 V from battery | J2 DC jack 5.5/2.1 mm · B240A reverse protection · SMBJ18A | Field battery (12 V lead, LiFePO4 or car) |
| 12 V from USB | U3 **TPS61085PWR** boost (from Pico VBUS), L 4.7 µH ≥ 2 A, B240A, FB divider for 12.0 V, enable from Pico | ≈ 1 W, about 250 mA from USB: within the 500 mA limit |
| Cable power | OR-ing (2 × B240A) → F1 MF-MSMF020-2 → SMBJ18A → RJ45 pins 4/5 | Cable short = the PTC trips, nothing burns |
| RS-485 | THVD1450DR · SM712-02HTG × 2 · 120 Ω termination | |
| Connector | Amphenol RJHSE-5380 | |
| Handle switch | 3.5 mm jack · 1 kΩ series, 100 nF, BAT54S clamp · Pico pull-up | Timestamped at the base to ~0.1 ms, which is plenty for the handle |
| Feedback | Piezo transducer, ~12 mm, 4 kHz, external drive (driven directly by the Pico's PWM) · LEDs: power, sensor link, pass | A beep per lap helps the timekeepers |
| MCU | Raspberry Pi Pico 2 module, its USB to the laptop | |
| Option | 6-pin header for a GPS module with PPS (e.g. Adafruit Ultimate GPS) | Calibrates both crystals against GPS time |

## 4. Enclosure (3D-printed, ASA or PETG, black)

- Sensor head: optical chamber with the original geometry (10 mm slit, 9–50° elevation, 150 mm to the detector).
  Inside lined with black flock paper. The slit is closed by a blue filter plus a clear polycarbonate rain window.
  Brass ¼″ thread insert for a camera tripod, a bubble level on top, and a sun-shade lip over the slit.
- Base station: a small ABS box, or printed.
- The enclosure is designed once the PCB outline is fixed (next step after the schematic).

## 5. Fabrication route (recommended)

**JLCPCB with assembly (PCBA):** upload the KiCad files and JLCPCB fits all the SMD parts, buying them from
LCSC. Every main chip on this list was in stock at LCSC on 2026-10-20 (see the parts list). You only buy and
solder the few through-hole and module parts yourself: Pico 2, BPW21R, RJ45, DC jack, audio jack, buzzer.

| Board | Layers | Quantity | Rough cost (5 boards, 2 assembled) |
|---|---|---|---|
| SH-1 sensor head | 4 | 5 | €70–120 incl. parts and assembly |
| BS-1 base station | 2 | 5 | €40–70 incl. parts and assembly |

## 6. Rough cost of one complete system

| Item | ≈ € |
|---|---|
| Sensor head board, assembled (with SCL3300, ADC, 1–2 photodiodes) | 70–110 |
| Base station board, assembled | 35–55 |
| 2 × Pico 2, connectors, buzzer | 25 |
| 80 m outdoor Cat5e + plugs | 40–70 |
| Enclosure printing, filter, window, tripod insert, bubble level | 20–35 |
| **Total for the first system** | **≈ 200–300** |

Further systems cost less, because PCB set-up costs are shared.

## 7. Parts list

Per board, with order links: [`hardware/sensor-head/bom.csv`](../hardware/sensor-head/bom.csv) and
[`hardware/base-station/bom.csv`](../hardware/base-station/bom.csv). Both CSV files can be uploaded directly to
the BOM tools at Mouser, DigiKey and LCSC (columns: MPN, quantity).

### 7a. What you buy yourself (JLCPCB route)

| Part | Qty | Order link | Notes |
|---|---|---|---|
| Raspberry Pi Pico 2 | 2 (+1 spare) | [raspberrypi.com, lists approved resellers](https://www.raspberrypi.com/products/raspberry-pi-pico-2/) | Not the Pico 2 **W** |
| Vishay BPW21R photodiode | 1–2 (+1 spare) | [Farnell 1045427](https://uk.farnell.com/vishay/bpw21r/photodiode-565nm-to-5/dp/1045427) · [DigiKey](https://www.digikey.com/en/products/result?keywords=BPW21R) | ≈ €10–12 each. The 2nd is for the dual-field option |
| Amphenol RJHSE-5380 RJ45 jack | 2 | [Farnell 1849916](https://uk.farnell.com/amphenol/rjhse-5380/modular-jack-rj45-cat5-shielding/dp/1849916) · [DigiKey](https://www.digikey.com/en/products/result?keywords=RJHSE-5380) | Through-hole; JLCPCB can also fit it if LCSC stocks it |
| DC jack 5.5 × 2.1 mm, PCB mount | 1 | [DigiKey search](https://www.digikey.com/en/products/result?keywords=barrel%20jack%205.5%202.1%20pcb) | Pick one with matching footprint at the KiCad stage |
| 3.5 mm stereo jack, PCB mount | 1 | [DigiKey search](https://www.digikey.com/en/products/result?keywords=3.5mm%20audio%20jack%20pcb) | Handle switch |
| Piezo transducer ~12 mm, 4 kHz, external drive, PCB pins | 1 | [DigiKey search](https://www.digikey.com/en/products/result?keywords=piezo%20transducer%204kHz%20external%20drive) | Murata PKM13EPYH4000-A0 was the first choice but looks discontinued; any equivalent fits |
| Outdoor Cat5e cable, 80 m, PE jacket, + RJ45 plugs | 1 | local electrical supplier or [DigiKey search](https://www.digikey.com/en/products/result?keywords=cat5e%20outdoor%20cable) | Buy locally: cheaper and no shipping of a heavy drum |
| IP67 RJ45 panel feed-through | 1 | [DigiKey search](https://www.digikey.com/en/products/result?keywords=RJ45%20IP67%20feedthrough) | Sensor head enclosure |

### 7b. What JLCPCB buys for you (main ICs, for reference and for hand-building)

| Part | SH-1 | BS-1 | LCSC (for JLCPCB) | Other distributors | Notes |
|---|---|---|---|---|---|
| TI **ADS131M04IPWR** 24-bit 4-ch ADC | 1 | | [C2862562](https://www.lcsc.com/product-detail/C2862562.html) | [DigiKey](https://www.digikey.com/en/products/result?keywords=ADS131M04IPWR) · [Mouser](https://www.mouser.com/c/?q=ADS131M04IPWR) | **DigiKey: out of stock until 03/2027.** LCSC ≈ 5000 and Mouser ≈ 3700 in stock |
| Microchip **MCP6022-I/SN** dual op-amp | 2 | | [C34047](https://www.lcsc.com/product-detail/C34047.html) | [DigiKey](https://www.digikey.com/en/products/result?keywords=MCP6022-I%2FSN) | 2nd only with D2 |
| TI **LP5907MFX-3.3/NOPB** low-noise LDO | 1 | | [C80670](https://www.lcsc.com/product-detail/C80670.html) | [DigiKey](https://www.digikey.com/en/products/result?keywords=LP5907MFX-3.3%2FNOPB) | |
| Diodes **AP63205WU-7** 5 V buck | 1 | | [LCSC search](https://www.lcsc.com/search?q=AP63205WU-7) | [DigiKey](https://www.digikey.com/en/products/detail/diodes-incorporated/AP63205WU-7/9858424) | |
| Murata **SCL3300-D01** inclinometer | 1 | | [LCSC search](https://www.lcsc.com/search?q=SCL3300-D01) | [Farnell 3018435](https://uk.farnell.com/murata/scl3300-d01/inclinometer-90deg-digital/dp/3018435) · [DigiKey](https://www.digikey.com/en/products/result?keywords=SCL3300-D01) | If LCSC has none, buy it yourself and JLCPCB fits it (consigned part) |
| TI **THVD1450DR** RS-485 transceiver | 1 | 1 | [C2671361](https://www.lcsc.com/product-detail/C2671361.html) | [DigiKey](https://www.digikey.com/en/products/detail/texas-instruments/THVD1450DR/9356550) | |
| Littelfuse **SM712-02HTG** RS-485 TVS | 2 | 2 | [C172881](https://www.lcsc.com/product-detail/C172881.html) | [DigiKey](https://www.digikey.com/en/products/result?keywords=SM712-02HTG) | |
| TI **TPS61085PWR** boost 5 → 12 V | | 1 | [C13505](https://www.lcsc.com/product-detail/C13505.html) | [DigiKey](https://www.digikey.com/en/products/result?keywords=TPS61085PWR) | |
| Bourns **MF-MSMF020-2** PTC fuse 200 mA | 1 | 1 | [C35456](https://www.lcsc.com/product-detail/C35456.html) | [DigiKey](https://www.digikey.com/en/products/result?keywords=MF-MSMF020-2) | |
| **SMBJ18A** TVS diode 18 V | 1 | 2 | [LCSC search](https://www.lcsc.com/search?q=SMBJ18A) | [DigiKey](https://www.digikey.com/en/products/result?keywords=SMBJ18A) | |
| Diodes **B240A-13-F** Schottky 2 A 40 V | 2 | 4 | [LCSC search](https://www.lcsc.com/search?q=B240A-13-F) | [DigiKey](https://www.digikey.com/en/products/result?keywords=B240A-13-F) | |
| Nexperia **BAT54S** dual Schottky | | 1 | [LCSC search](https://www.lcsc.com/search?q=BAT54S) | [DigiKey](https://www.digikey.com/en/products/result?keywords=BAT54S%2C215) | |
| Inductor 4.7 µH, I_sat ≥ 2.5 A, shielded ~5×5 mm | 1 | 1 | chosen from JLCPCB stock in KiCad | | AP63205 value from its datasheet |
| Resistors, capacitors 0603/0805, ferrite beads, LEDs | ~45 | ~30 | JLCPCB "basic" parts | | Exact list comes out of the KiCad schematic. Rf: 0.1 % thin film; Cf, C1, ADC RC: C0G |

LCSC "search" links open LCSC's own search page, which builds itself in the browser. The C-number links go straight to the product.

### 7c. European sellers and stock audit (2026-10-20)

[TME](https://www.tme.eu) (Poland) covers almost everything. Exceptions are the ADC, which needs Mouser Europe or the
TI store, and the buck converter, which needs Farnell. Mouser and DigiKey ship to the EU with duties included,
but from the USA.

| Part | European seller | Stock found | Audit note |
|---|---|---|---|
| ADS131M04IPWR | [Mouser EU](https://eu.mouser.com/c/?q=ADS131M04IPWR) · [TI store](https://www.ti.com/product/ADS131M04) · LCSC via JLCPCB | Mouser 1–4 k (reported); LCSC ≈ 5 k | ⚠ **TME: special order in multiples of 250 only.** ⚠ DigiKey: none until 03/2027 |
| MCP6022-I/SN | [TME search](https://www.tme.eu/en/katalog/?art=MCP6022-I%2FSN) | | The DIP version is in stock at TME (bench test) |
| LP5907MFX-3.3/NOPB | [TME](https://www.tme.eu/en/details/lp5907mfx-3.3_nopb/ldo-fixed-voltage-regulators/texas-instruments/) | listed | |
| AP63205WU-7 | [Farnell](https://uk.farnell.com/diodes-inc/ap63205wu-7/switching-regulator-syn-buck-tsot/dp/3518308) | Farnell ≈ 6 k | ⚠ **TME: 0 in stock** |
| SCL3300-D01 | [Farnell DE](https://de.farnell.com/en-DE/murata/scl3300-d01/mems-modul-3-achsen-neigungswinkelmesser/dp/3018435) · [TME (SCL3300-D01-1)](https://www.tme.eu/en/details/scl3300-d01-1/tilt-sensors/murata-power-solutions/) | listed | The suffix (-1, -004, -10) is only the reel size; same sensor |
| THVD1450DR | [TME](https://www.tme.eu/en/details/thvd1450dr/rs232-rs422-rs485-integr-circ/texas-instruments/) | listed | |
| SM712-02HTG | [TME](https://www.tme.eu/en/details/sm712-02htg-lf/protection-diodes-arrays/littelfuse/sm712-02htg/) | TME 1 814 | |
| TPS61085PWR | [TME (TPS61085**PW**)](https://www.tme.eu/en/details/tps61085pw/voltage-regulators-dc-dc-circuits/texas-instruments/) | listed | PW = tube, PWR = reel: same chip and footprint |
| MF-MSMF020-2 | [TME](https://www.tme.eu/en/details/mf-msmf020-2/smd-polymer-fuses/bourns/) | listed | 30 V max, above the 18 V TVS ✓ |
| B240A-13-F | [TME](https://www.tme.eu/en/details/b240a-13-f/smd-schottky-diodes/diodes-incorporated/) | listed | |
| SMBJ18A, BAT54S | [TME SMBJ18A](https://www.tme.eu/en/katalog/?art=SMBJ18A) · [TME BAT54S](https://www.tme.eu/en/katalog/?art=BAT54S) | | Standard parts, many makers |
| RJHSE-5380 | [TME](https://www.tme.eu/en/details/rjhse-5380/rj-connectors/amphenol/) | TME 1 072 | |
| BPW21R | [TME](https://www.tme.eu/en/details/bpw21r/photodiodes/vishay/) | TME ≈ 600 | Not Reichelt's "BPW 21" (a different part) |
| Raspberry Pi Pico 2 (SC1631) | [TME](https://tme.eu/en/details/sc1631/raspberry-pi-minicomputers/raspberry-pi/raspberry-pi-pico-2) · [Electrokit (SE)](https://www.electrokit.com/en/raspberry-pi-pico-2) · [Kiwi (NL)](https://www.kiwi-electronics.com/en/raspberry-pi-pico-2-20128) · [Pimoroni (UK)](https://shop.pimoroni.com/products/raspberry-pi-pico-2) | Electrokit ≈ 2 500 | |

**Design check done during the audit:** voltage ratings line up. The cable input is 9–18 V; SMBJ18A clamps at ≈ 29 V,
which is below the 32 V maximum of the AP63205 and above the 18 V working voltage; the PTC is rated 30 V. The
SCL3300 runs at 3.0–3.6 V, the same as the Pico's 3.3 V. The ADC accepts 1–8.3 MHz CLKIN, which covers the planned 7.5 MHz.
Still to check when the schematic is drawn: the TPS61085 inductor value, and the exact fit of the DC and audio jack footprints.

## 8. Order of work, and when to buy

1. **Now:** only the bench-test parts ([bench-test.md §2](bench-test.md#2-parts-list), ≈ €30). Do **not** order
   the PCB parts yet; the ⚑ values may change.
2. Bench test: measure photocurrent, noise and model dip.
3. KiCad schematic of SH-1 and BS-1 with the measured values, followed by a review.
4. PCB layout, then a JLCPCB order (5 + 5 boards, 2 + 2 assembled). **Buy the Pico 2s, BPW21Rs and connectors at that point.**
5. Enclosure design and printing, firmware (sensor detection + base station), then a field test against manual timing.
