# CLI limit contract

The public command accepts an optional `--limit` value. Existing callers use
an omitted value and an empty environment value differently: omission means
the default page size, while an empty value has historically meant unlimited.

Any change to the shared parser must choose whether that distinction remains
part of the public interface.

The legacy adapter passes its value through to this shared parser, so changing
the empty-string meaning changes existing callers as well.
