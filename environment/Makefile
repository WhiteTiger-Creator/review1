CXX = g++
CXXFLAGS = -std=c++20 -O2 -pipe -Wall -Wextra -Wpedantic

all: bin/hull4_facet_profile

bin/hull4_facet_profile: src/main.cpp
	mkdir -p bin
	$(CXX) $(CXXFLAGS) src/main.cpp -o bin/hull4_facet_profile

clean:
	rm -rf bin
