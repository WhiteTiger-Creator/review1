use crate::types::{ByteView, ChannelView};

pub fn legacy_nx_copy(src: &ByteView, names: &[String]) -> ChannelView {
    let n = names.len();
    let mut bytes = src.data.to_vec();
    if bytes.len() < n * 4 {
        bytes.resize(n * 4, 0);
    }
    ChannelView {
        bytes,
        names: names.to_vec(),
        present: vec![true; n],
    }
}
