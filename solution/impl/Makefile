CXX = g++
CXXFLAGS = -std=c++17 -Wall -Wextra -O2 -I./inc
LDFLAGS = -lcrypto

SRCS = src/main.cpp src/config.cpp src/json_util.cpp src/crypto.cpp \
       src/verifier.cpp src/report.cpp
OBJS = $(SRCS:.cpp=.o)
BIN = bin/tuf-rollout-verifier

all: $(BIN)

$(BIN): $(OBJS)
	@mkdir -p bin
	$(CXX) $(OBJS) -o $(BIN) $(LDFLAGS)

src/%.o: src/%.cpp
	$(CXX) $(CXXFLAGS) -c $< -o $@

clean:
	rm -f $(OBJS) $(BIN)

.PHONY: all clean
