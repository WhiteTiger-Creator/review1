fn main() {
    println!("{}|{}|{}|{}", adapter::adapter(), audit_format::format_id(),
        audit_proto::proto_id(), build_helper::helper());
}
