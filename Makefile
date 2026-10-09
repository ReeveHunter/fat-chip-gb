# gbmidi - build with GBDK-2020 (https://github.com/gbdk-2020/gbdk-2020)
#   make GBDK_HOME=/path/to/gbdk
GBDK_HOME ?= $(HOME)/gbdk
LCC   = $(GBDK_HOME)/bin/lcc
PY   ?= python3

ROM   = gbmidi.gb
BUILD = build

CFLAGS  = -Isrc -Wf--opt-code-speed -Wf--max-allocs-per-node50000
LDFLAGS = -Wl-yt0x03 -Wl-yo16 -Wl-ya1 -Wm-yn"GBMIDI"

GEN = src/gen/tables.c src/gen/waves.c src/gen/names.c \
      src/gen/drums.c src/gen/drum_names.c \
      src/gen/speech.c src/gen/speech_tbl.c src/gen/speech_names.c \
      src/gen/font.c

SRC_C = $(wildcard src/*.c) $(GEN)
SRC_S = $(wildcard src/*.s)
DRUM_BANKS = $(wildcard src/gen/drums_bank*.c)
OBJ = $(patsubst %.c,$(BUILD)/%.o,$(SRC_C) $(DRUM_BANKS)) $(patsubst %.s,$(BUILD)/%.o,$(SRC_S))

all: $(ROM)

gen: $(GEN)

src/gen/tables.c src/gen/waves.c src/gen/names.c: tools/gen_tables.py tools/cgen.py
	$(PY) tools/gen_tables.py
src/gen/drums.c src/gen/drum_names.c: tools/gen_drums.py tools/cgen.py
	$(PY) tools/gen_drums.py
src/gen/speech.c src/gen/speech_tbl.c src/gen/speech_names.c: tools/gen_speech.py tools/cgen.py
	$(PY) tools/gen_speech.py
src/gen/font.c: tools/gen_font.py res/font8x8_basic.h
	$(PY) tools/gen_font.py

$(BUILD)/%.o: %.c src/engine.h
	@mkdir -p $(dir $@)
	$(LCC) $(CFLAGS) -c -o $@ $<

$(BUILD)/%.o: %.s
	@mkdir -p $(dir $@)
	$(LCC) -c -o $@ $<

$(ROM): $(OBJ)
	$(LCC) $(LDFLAGS) -Wl-m -Wl-j -o $@ $(OBJ)

clean:
	rm -rf $(BUILD) $(ROM) gbmidi.map gbmidi.noi gbmidi.sym

.PHONY: all gen clean
