.PHONY: install compile-check starter-check clean

SRC_ROOT := /app/src
CLASSES_NEXT := /app/.glideclasses.next
JAR_NEXT := /app/lib/.glideclash.next.jar
JAR := /app/lib/glideclash.jar
SOURCE_LIST := /tmp/glideclash_sources.txt
SMOKE_DIR := /tmp/glideclash_smoke
LOAD_DIR := /tmp/glideclash_load

define collect_sources
	find "$(SRC_ROOT)" -name '*.java' | LC_ALL=C sort > "$(SOURCE_LIST)"
endef

install:
	@set -e; \
	rm -rf "$(CLASSES_NEXT)" "$(JAR_NEXT)" "$(LOAD_DIR)"; \
	mkdir -p "$(CLASSES_NEXT)" /app/lib "$(LOAD_DIR)"; \
	$(collect_sources); \
	if ! javac --release 17 -Xlint:all -Werror -d "$(CLASSES_NEXT)" @"$(SOURCE_LIST)"; then \
		rm -rf "$(CLASSES_NEXT)" "$(JAR_NEXT)"; \
		exit 1; \
	fi; \
	if ! jar --create --file "$(JAR_NEXT)" -C "$(CLASSES_NEXT)" .; then \
		rm -rf "$(CLASSES_NEXT)" "$(JAR_NEXT)"; \
		exit 1; \
	fi; \
	printf '%s\n' \
		'public final class _GlideLoadCheck {' \
		'  public static void main(String[] args) throws Exception {' \
		'    Class.forName("glideclash.api.Engine");' \
		'    Class.forName("glideclash.api.Blueprint");' \
		'    Class.forName("glideclash.api.GlideFrame");' \
		'    Class.forName("glideclash.api.InputFrame");' \
		'    Class.forName("glideclash.api.Snapshot");' \
		'  }' \
		'  private _GlideLoadCheck() {}' \
		'}' > "$(LOAD_DIR)/_GlideLoadCheck.java"; \
	if ! javac --release 17 -d "$(LOAD_DIR)" "$(LOAD_DIR)/_GlideLoadCheck.java" \
		|| ! java -cp "$(LOAD_DIR):$(JAR_NEXT)" _GlideLoadCheck; then \
		rm -rf "$(CLASSES_NEXT)" "$(JAR_NEXT)" "$(LOAD_DIR)"; \
		exit 1; \
	fi; \
	mv "$(JAR_NEXT)" "$(JAR)"; \
	rm -rf "$(CLASSES_NEXT)" "$(LOAD_DIR)"

compile-check:
	rm -rf /tmp/glideclash_compile_check
	mkdir -p /tmp/glideclash_compile_check
	$(collect_sources)
	javac --release 17 -Xlint:all -Werror -d /tmp/glideclash_compile_check @"$(SOURCE_LIST)"
	rm -rf /tmp/glideclash_compile_check

starter-check: install
	rm -rf "$(SMOKE_DIR)"
	mkdir -p "$(SMOKE_DIR)"
	javac --release 17 -cp "$(JAR)" -d "$(SMOKE_DIR)" /app/examples/SmokeHarness.java
	java -cp "$(SMOKE_DIR):$(JAR)" SmokeHarness
	rm -rf "$(SMOKE_DIR)"

clean:
	rm -rf "$(CLASSES_NEXT)" "$(JAR_NEXT)" /tmp/glideclash_compile_check "$(SMOKE_DIR)" "$(LOAD_DIR)"
	rm -f /app/examples/*.class "$(SOURCE_LIST)"
