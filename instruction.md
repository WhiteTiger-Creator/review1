One of the LP-series access controllers came back from a site with nobody left who remembers
its unlock code, and the vendor folded years ago. What we have is the flash image, the core
datasheet at /app/docs/kx8-datasheet.md, and the notes we keep on our own workbench tool at
/app/docs/kxtool-contract.md. Nothing off the shelf makes sense of this core, so the Rust
project in /app is where the work goes: `make` there builds it and leaves the binary at
/app/bin/kxtool. Two boards' images, plus one that came off the programmer damaged, are in
/app/samples.

Four things have to work. Disassemble a window of an image. Run an image against a key
stream and report what the board did with it. Describe an image and what running it changes.
And recover the unlock code the image accepts. Boards differ — code, constants, layout — so
this has to hold for any image that fits the container, not only for the two samples, and an
image that does not check out gets refused rather than executed.

The contract fixes what the tool prints, down to the text of a disassembly line. Read the
datasheet closely but do not take it on faith — it is a revision behind the parts we
actually have, and /app/samples/conformance holds a bench capture off one of those parts
along with the ROMs it was taken from. Your model of the core has to reproduce that capture
exactly, cycle counts and all, before anything it tells you about a board is worth
believing. Standard library only, no new dependencies, no network, and leave the images in
/app/samples as you found them.
