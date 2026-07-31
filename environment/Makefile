CXX = g++
CXXFLAGS = -Wall -Wextra -O2 -std=c++17 -Iinclude
LDFLAGS = -lssl -lcrypto

OBJS = build/main.o build/qdrift_cli_dispatch.o build/qgraph_loader.o \
       build/topo_schedule.o build/interval.o build/mx_ops.o build/layer_step.o \
       build/wdtype.o build/qstep.o build/interval_walker.o build/gate_epoch.o \
       build/json_emit.o build/qdrift_staging_io.o build/witness_seal.o

all: build/qbound-analyzer

build:
	mkdir -p build

build/main.o: src/main.cpp | build
	$(CXX) $(CXXFLAGS) -c $< -o $@
build/qdrift_cli_dispatch.o: src/qdrift_cli_dispatch.cpp | build
	$(CXX) $(CXXFLAGS) -c $< -o $@
build/qgraph_loader.o: src/qgraph_loader.cpp | build
	$(CXX) $(CXXFLAGS) -c $< -o $@
build/topo_schedule.o: walk/topo_schedule.cpp | build
	$(CXX) $(CXXFLAGS) -c $< -o $@
build/interval.o: src/interval.cpp | build
	$(CXX) $(CXXFLAGS) -c $< -o $@
build/mx_ops.o: kernel/mx_ops.cpp | build
	$(CXX) $(CXXFLAGS) -c $< -o $@
build/layer_step.o: kernel/layer_step.cpp | build
	$(CXX) $(CXXFLAGS) -c $< -o $@
build/wdtype.o: numeric/wdtype.cpp | build
	$(CXX) $(CXXFLAGS) -c $< -o $@
build/qstep.o: numeric/qstep.cpp | build
	$(CXX) $(CXXFLAGS) -c $< -o $@
build/interval_walker.o: src/interval_walker.cpp | build
	$(CXX) $(CXXFLAGS) -c $< -o $@
build/gate_epoch.o: policy/gate_epoch.cpp | build
	$(CXX) $(CXXFLAGS) -c $< -o $@
build/json_emit.o: catalog/json_emit.cpp | build
	$(CXX) $(CXXFLAGS) -c $< -o $@
build/qdrift_staging_io.o: src/qdrift_staging_io.cpp | build
	$(CXX) $(CXXFLAGS) -c $< -o $@
build/witness_seal.o: catalog/witness_seal.cpp | build
	$(CXX) $(CXXFLAGS) -c $< -o $@

build/qbound-analyzer: $(OBJS)
	$(CXX) $(OBJS) -o $@ $(LDFLAGS)

clean:
	rm -rf build

.PHONY: all clean
