.PHONY: engrave clean

PARCELS ?= /app/parcels
OUT ?= /app/out

engrave:
	valac /app/engraver/*.vala -o /app/engraver/engraver
	/app/engraver/engraver "$(PARCELS)" "$(OUT)"

clean:
	rm -f /app/out/crate.index /app/out/seal.manifest /app/engraver/engraver
	find /app/engraving_tmp -mindepth 1 ! -name .keep -delete
