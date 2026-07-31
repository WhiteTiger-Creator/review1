edge-07 dropped power in the middle of an overnight DPX/1 upgrade run and came back up in a
state nobody trusts. `dpx verify` is unhappy about it and the rest of the rollout is queued
behind this box. Get it back to consistent, with the interrupted run properly closed out.

Nineteen more boxes went down with it and I'm not doing this by hand nineteen times, so the
fix has to be a thing we can ship: put it at /usr/local/sbin/dpx-reconcile, one argument
which is the root of the install, exit 0 once it's done and that root is consistent. It has
to be safe to run twice. Then run it here — this box's root is /.

Worth saying: DPX/1 makes a set of promises about what lives on a machine, and none of them
stop applying just because a run got cut in half. They're written up at
/usr/local/share/doc/dpx/dpx-1.md. Whatever you do to tidy this up has to still keep every
one of them. No network on the box.
