# BB-LAN — Bubble Bobble voor 2 spelers over het LAN

Bubble Bobble (C64) omgebouwd voor coöperatief spel over het netwerk. Elke speler heeft een
eigen C64: VICE, een C64 Ultimate/Ultimate 64, of later een C64 met WiC64. Beide machines
draaien het spel in lockstep en wisselen via een gameserver alleen joystick-input uit.

> Status: **fase 0**. De originele game bouwt en draait; er is nog geen netwerkcode.
> Zie [docs/PLAN.md](docs/PLAN.md) voor het volledige plan.

## Bouwen

Benodigd: Python 3 en cc65 (ca65/ld65). De build zoekt cc65 in `$CC65_HOME/bin`, daarna in
`../c64/cc65/bin` naast deze repo, daarna in `PATH`.

```bash
python tools/build.py              # build/rebb64-raw.prg (ruwe image $0400-$FFFA)
python tools/build.py verify       # + SHA256-check: identiek aan het origineel
python tools/build.py release      # + build/bblan.prg (zelfuitpakkend, LOAD/RUN)
python tools/build.py clean
```

`bblan.prg` laadt als gewone BASIC-PRG (`LOAD"BBLAN",8` + `RUN`, of autostart in VICE).
De packer (`tools/pack.py` + `tools/sfx.s`) zit in de repo, dus er is geen externe cruncher nodig.

## Credits

- Gebaseerd op [rebb64](https://github.com/zaidka/rebb64) van zaidka: de gereconstrueerde,
  herbouwbare broncode van de C64-versie. De originele README staat in
  [docs/REBB64-README.md](docs/REBB64-README.md).
- Bubble Bobble © Taito. C64-versie door Software Creations, uitgegeven door Firebird.
- De netwerkcode en gameserver komen uit het WoW-LAN-project (Wizard of Wor LAN).
