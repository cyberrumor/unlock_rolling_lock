# unlock rolling locks

This project is a collection of reverse engineered keys for publicly accessible
rolling locks.

# Wcostream

Proof of concept for client side deobfuscation of rolling lock algorithm resulting
in information disclosure and file download.

Wcostream is a video streaming website. They host videos directly from remote storage,
and provide clients with obfuscated URLs to the asset locations. These obfuscation
algorithms are different on every page, and appear to be generated pragmatically.

I recommend files be hosted from links that are considered safe to disclose publicly,
These links should be generated server side and delivered only after confirmation that
a client has downloaded an ad.

The links should be delivered in plain text (thus simplifying your front end). The
server-side handler for the link should request the file from the actual storage
location, and forward streams to the client, thus preventing information disclosure.

The storage should be configured in a way that only provides access to the server.

Data should only be allowed to be streamed at a rate consistent with slightly above
the normal speed for watching videos, thus discouraging automation.

