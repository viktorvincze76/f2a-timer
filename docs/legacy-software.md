# The old timing software (Transitrace TT): what it does

Reference for the new contest software (roadmap step 5). It describes the old program as found on the club's
DOS PC: **Transitrace Speed Timing, TT.EXE "Version II 4.04", compiled 17 Oct 2015** by Göran Olsson, built with
Microsoft C. Sources for this description:

- `INSTRUCT.TXT` (the program's own manual) and `RULES.TXT` (FAI F2A rules, 2014), shipped with it
- the user-facing text inside `TT.EXE`
- **250 logged flights from 2014–2026** (including the 2014 World Championships and Mecsek kupa 2025), used to
  check every rule below. All 117 electronic results in the logs are reproduced exactly by the formulas here.

The exe has not been disassembled. Nothing below needed it.

## 1. Files it uses

All plain text, CRLF line endings, code page 852 (Hungarian DOS), in the program folder.

| File | Contents |
|---|---|
| `*.TTC` | One **category** per file (14 shipped: F2A, F2C, AMA-…, SWE-…, RC200M, TCAR). 13 lines, value then comment, see §2 |
| `NN<name>.TXT` | **Name registry** = competitor list for one contest. Line `0<TAB><headline>` is the contest name (max 15 chars), then `<number><TAB><name>` per competitor. Club/country is typed into the name, e.g. `Gofast Marlon JUN (SWE)` |
| `NF.TXT` | Which name registry is in use |
| `TTyymmdd.TXT` | **Flight log**, one per day, every attempt appended. This is the only results storage, see §5 |
| `TT.TTT` | PC settings: timer clock frequency (from `TTCAL.EXE`), screen mode, plot style, parallel port address |
| `INSTRUCT.TXT`, `RULES.TXT` | Shown by the Help menu, 20 lines per page; meant to be translated/edited by users |

## 2. Category settings (`.TTC`)

`F2A.TTC` as an example:

| Field | F2A | Meaning |
|---|---|---|
| Category name | `FAI-F2A` | one word |
| Timed laps | 9 | laps in the official flight |
| Speed formula | 3600 | speed = this / time; 3600 with 9 laps = km/h over 1 km |
| Unit | km/h | |
| Attempt time | 3 min | countdown for the pilot to engage the pylon |
| Count-in laps | 2 | laps after handle engage before timing starts |
| Start on release | 0 | 1 = timing starts at model release (AMA proto classes) |
| Maximum speed | 340 | sanity limit; also used to filter stray pulses |
| Stopwatch tolerance | 0.12 s | manual timekeeper agreement limit |
| Round-off | 1 | 1 dec trunc / 1 dec round / 2 dec trunc / 2 dec round / 3 dec round |
| Display | 0 | show lap speeds (0) or lap times (1) |
| Sensor radius | 21.5 m | shown as a reminder whenever the category changes |

Other categories differ only in values (e.g. `SWE-A`: 11 laps, 240 km/h max, sensor at 18.0 m).

## 3. Timing rules, as the logs show them

Checked against all logged flights (a check script run over the logs; not in the repo because the logs hold real names):

- **Start of timing:** the last handle-engage event, then the first sensor pass after it, then *count-in* more passes.
  Timing starts at that pass. If the handle is disengaged and re-engaged, the **last** engage counts.
- **Electronic time** = timestamp of the pass ending lap (start + 9) − timestamp of the start pass.
- **Result** = 3600 / time, **truncated** to 0.1 km/h (FAI 4.1.17 "nearest lower 1/10"). E.g. 13.1062 s →
  274.678 → **274.6**.
- **Course speed** (log and screen): rolling speed over the last 9 laps, shown for every lap from lap 9 on.
- **Best laps**: the screen also shows the fastest 9 consecutive laps of the whole flight.
- **Auto mode** (round 0): no handle; the first sensor hit starts timing. Used for practice.
- **Limits**: max 318 laps per flight; pulses too close together for the category's max speed are removed.

## 4. Features, screen by screen

**Main menu:** C Contest · A Auto · L view Log · X category · N Names · T Test · S Screen · E Evaluate ·
Y sysinfo · H Help · M Message · Q Quit

| Feature | What it does | New software |
|---|---|---|
| **Startup checks** | Warns if PC date/year looks wrong or it's night; refuses timing under Windows | Keep the clock check (logs are named by date). Drop the Windows check |
| **Category** (X) | Pick a `.TTC`; always warns that the sensor may need moving and shows the radius | Keep, as a categories table/file. Keep the warning |
| **Names** (N) | Show registry; add/edit name; set headline; switch registry; save as new | Keep. Add separate fields for country/club, junior, licence number instead of packing them into the name |
| **Contest** (C) | Shows category, round, attempt; change R/A; enter competitor number; asks for name if unknown. Then: start by handle switch or S; change entry | Keep |
| **Flight screen** | 3:00 countdown; state (Waiting, Flying, Counting-in, Official run, Landed…); lap table with speed or time; space = engage, V = disengage if no switch; B = break | Keep. Handle switch and sensor now come from the Pico |
| **Flight events** | Messages for: count-in cancelled, handle disengaged during timed laps, attempt timed out, "few or no laps flown, log it?" | Keep all |
| **After the flight** | Result shown automatically; L list, P plot | Keep |
| **Shift** (S) | Move the timed 9 laps ±n laps (wrong handle judging). Logged as `$ Manual Shift: n` | Keep |
| **Missed lap** (I) | Detects a doubled lap time and *warns*; operator enters the lap number to split. Refuses if "times are too irregular". Logged as `$ Missed lap inserted` | Keep as operator decision (see §6) |
| **Validate** (V) | Enter up to 3 stopwatch times; applies FAI 4.1.17 (mean, drop one outside 0.12 s, two disagreeing → choose, one left → notify competitor of re-attempt right); shows manual-vs-electronic difference; ruling **E**lectronic / **M**anual / **A**ttempt / **C**ancelled | Keep exactly; it encodes the rules |
| **Comment** (C) | Free text for the log | Keep |
| **Next / Main** (N/M) | Must press twice, against accidents | Keep the idea (confirm) |
| **Log review** (L) | Pick a day; **survey** table (flight, comp, name, time, round, attempt, category, result, ruling) with each competitor's best; open a flight: time stamps, list, plot, **replay** | Keep. Survey becomes the base of a results table |
| **Auto** (A) | Practice timing without handle, round 0 | Keep |
| **Evaluate** (E) | Training mode: Z key simulates a sensor pass | Already exists as `--sim`; keep a key-press sim for training |
| **Message** (M) | Sends a text to an external LED display (the code contains a moving-message sign protocol) | Ask the club whether a display board is still used |
| **Test** (T) | Plot test, sound alarm on the sensor jack, sensor/handle/battery test, PC timer test | Keep sensor/handle test (now via Pico). Drop PC timer and plot tests |
| **Screen** (S) | 6 colour schemes, 3 plot styles | Replace with a high-contrast theme for sunlight |
| **Sysinfo** (Y) | Port, timer, pulse statistics, filtered pulses | Keep as diagnostics (Pico version, dropped events, filtered pulses) |
| **Help** (H) | Pages through INSTRUCT/RULES | Keep or link to docs |
| **Secondary sensor** | Shown in tests and replay ("not supported yet") | Roadmap item 7 (dual slit) |

## 5. Log file format (`TTyymmdd.TXT`)

One block per attempt, blank lines between. Tab-separated.

```
# TT	F2A	Mon Jan 10 2000	10:07:30	Round:   1	Example cup
# Comp:	5	Gofast Marlon			Attempt: 1
# ETime	MTime1	MTime2	MTime3	ESpeed	MSpeed	EResult	MResult	Ruling
13.1062	 0.00	 0.00	 0.00	274.678	  0.000	274.6	  0.0	$ Electronic
# Timed Flight Laps:  9 - 17		[$ Manual Shift:  n]
# Individual laps:
# Lap   Speed(km/h) Time Stamp  Course Speed(km/h)
  0		   27.1806958
  1	154.687	   29.7665662
  …
  9	285.003	   42.2849129	238.344		[$ Missed lap inserted]
# Handle Events:
# Engaged   	    …
# Disengaged	    …
```

Ruling is one of Electronic, Manual, Attempt, Cancelled, or empty (not validated). Time stamps are seconds since
the attempt started. **An importer for this format is easy** and would bring 10+ years of club history and the
2014 World Championship logs into the new software, and give a large real-world test set for the timing logic.

## 6. Decisions and what is built

Decided October 2026; implemented in `host/f2atimer/` (`fai.py`, `contest.py`, `results.py`, `legacy.py`,
command `f2a-contest`).

1. **Overall results table: yes.** Individual classification with the FAI tie-break (2nd, then 3rd best speed,
   4.1.18), shared places for exact ties, a junior classification, and team classification (4.1.19: sum of best
   speeds; ties by lower sum of places, then best individual place). Text and a printable A4 HTML page.
2. **Laps follow the FAI rules.** A missed lap is detected and reported, never corrected automatically: the speed
   judge confirms it (4.1.17), then the lap is split, and the timed laps show it was inserted. Detection only looks
   from the handle engage to the end of the timed laps and needs steady laps on both sides, so take-off and landing
   laps do not trigger it. Stopwatch rules (4.1.17 a) are implemented as written, including when the competitor must
   be told of the right to a replacement attempt.
3. **Data model:** one contest file (JSON) holds competitors and every attempt, with raw passes and handle events
   kept unchanged; shifts and inserted laps are stored as corrections on top. A validated result is frozen, so a
   later software change cannot alter a published result. Files are written atomically.
4. **Old data can be imported** (`f2a-contest import-legacy`). Re-evaluating all 121 timed flights in the club's logs
   with the new code gives the same timed laps, time and speed as the old program, for every one of them.
   Clubs often never changed the round number in the old program, so many competitors have several official flights
   "in round 1"; the importer gives each extra one the next free round and notes this on the attempt.
5. **Personal data (GDPR):** real logs, name registries and contest files are never committed (see `.gitignore`).
   Tests use real flights anonymised with `host/tools/anonymise_tt_log.py`: names and numbers replaced, dates moved
   to 2000, comments dropped.
6. **System files:** the old program and the DOS files stay out of the repository.

Still open: the live contest screen (start an attempt, Pico timing, validation keys), start-on-release for proto
classes (needs a "model released" key), the LED display board, and a GUI (roadmap step 6).
