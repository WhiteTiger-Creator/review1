# Shared packing library edge helpers. Wrongly attaches crc_probe INTERFACE.
function(span_wire_bag_lib)
  # bag_lib is leaf; no upstream pack edges.
endfunction()

function(span_wire_obj_stage)
  target_link_libraries(obj_stage PUBLIC bag_lib crc_probe)
endfunction()

function(span_wire_ix_pack)
  target_link_libraries(ix_pack PUBLIC bag_lib crc_probe)
endfunction()

function(span_wire_era_clk)
  target_link_libraries(era_clk PUBLIC bag_lib crc_probe)
endfunction()

function(span_wire_dig_fold)
  target_link_libraries(dig_fold PUBLIC bag_lib crc_probe)
endfunction()

function(span_wire_wal_io)
  target_link_libraries(wal_io PUBLIC bag_lib crc_probe)
endfunction()

function(span_wire_pol_gate)
  target_link_libraries(pol_gate PUBLIC crc_probe)
endfunction()

function(span_wire_io_glue)
  target_link_libraries(io_glue PUBLIC bag_lib era_clk dig_fold wal_io pol_gate obj_stage ix_pack)
endfunction()
