package com.acme.lineage.dot;

import java.util.ArrayList;
import java.util.List;

public final class DotLexer {
    public enum Kind { ID, LBRACE, RBRACE, LBRACK, RBRACK, EQUALS, COMMA, SEMI, ARROW, EOF }

    public static final class Token {
        public final Kind kind;
        public final String text;
        public Token(Kind kind, String text) { this.kind = kind; this.text = text; }
    }

    private DotLexer() {}

    public static List<Token> lex(String src) {
        List<Token> tokens = new ArrayList<>();
        int i = 0, n = src.length();
        while (i < n) {
            char c = src.charAt(i);
            if (Character.isWhitespace(c)) { i++; continue; }
            if (c == '/' && i + 1 < n && src.charAt(i + 1) == '/') {
                while (i < n && src.charAt(i) != '\n') i++;
                continue;
            }
            if (c == '#') { while (i < n && src.charAt(i) != '\n') i++; continue; }
            if (c == '{') { tokens.add(new Token(Kind.LBRACE, "{")); i++; continue; }
            if (c == '}') { tokens.add(new Token(Kind.RBRACE, "}")); i++; continue; }
            if (c == '[') { tokens.add(new Token(Kind.LBRACK, "[")); i++; continue; }
            if (c == ']') { tokens.add(new Token(Kind.RBRACK, "]")); i++; continue; }
            if (c == '=') { tokens.add(new Token(Kind.EQUALS, "=")); i++; continue; }
            if (c == ',') { tokens.add(new Token(Kind.COMMA, ",")); i++; continue; }
            if (c == ';') { tokens.add(new Token(Kind.SEMI, ";")); i++; continue; }
            if (c == '-' && i + 1 < n && src.charAt(i + 1) == '>') {
                tokens.add(new Token(Kind.ARROW, "->")); i += 2; continue;
            }
            if (c == '"') {
                StringBuilder sb = new StringBuilder();
                i++;
                while (i < n) {
                    char d = src.charAt(i);
                    if (d == '\\' && i + 1 < n) { sb.append(d); sb.append(src.charAt(i + 1)); i += 2; continue; }
                    if (d == '"') { i++; break; }
                    sb.append(d); i++;
                }
                tokens.add(new Token(Kind.ID, DotEscaper.unescape(sb.toString())));
                continue;
            }
            int start = i;
            while (i < n) {
                char d = src.charAt(i);
                if (Character.isWhitespace(d) || d == '{' || d == '}' || d == '[' || d == ']'
                        || d == '=' || d == ',' || d == ';'
                        || (d == '-' && i + 1 < n && src.charAt(i + 1) == '>')) break;
                i++;
            }
            tokens.add(new Token(Kind.ID, src.substring(start, i)));
        }
        tokens.add(new Token(Kind.EOF, ""));
        return tokens;
    }
}
