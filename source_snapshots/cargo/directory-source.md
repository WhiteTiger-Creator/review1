# Source: https://doc.rust-lang.org/cargo/reference/source-replacement.html
# Retrieved: 2026-07-21
# Title: Directory Sources
# Bounded task rule: Unpacked crate directories plus .cargo-checksum.json; verify package identity, listed files, package checksum, reject unexpected files and unsafe symlinks.

Directory sources contain the unpacked version of *.crate files.
Each crate in a directory source also has an associated metadata file .cargo-checksum.json to protect against accidental modifications.
A directory source is just a directory containing a number of other directories which contain the source code for crates.
