# Emit binary edge helpers. Wrongly attaches crc_probe to seal binaries.
function(span_wire_layer_emit)
  target_link_libraries(layer_emit PRIVATE io_glue crc_probe)
endfunction()

function(span_wire_yseal)
  target_link_libraries(yseal PRIVATE io_glue crc_probe)
endfunction()
