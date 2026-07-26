package com.acme.lineage.util;

import java.util.ArrayList;
import java.util.List;

public final class Csv {
    private Csv() {}

    public static List<String> split(String line) {
        List<String> out = new ArrayList<>();
        int start = 0;
        for (int i = 0; i < line.length(); i++) {
            if (line.charAt(i) == ',') {
                out.add(line.substring(start, i));
                start = i + 1;
            }
        }
        out.add(line.substring(start));
        return out;
    }
}
