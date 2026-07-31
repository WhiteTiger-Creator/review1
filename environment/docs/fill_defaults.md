# Fill defaults

Additive nullable names share one default on the offline materializer path and the online serving path.

Name w_n uses default zero point one two five as an f32.

When a nullable name is absent from a source blob, write that default into its canonical slot on both paths.

Do not write a plain zero on one path while using the documented default on the other.

Names that are not listed here stay untouched only when the catalog does not require them.
