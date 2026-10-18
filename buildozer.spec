[app]
title = Escale
package.name = escale
package.domain = org.axel
source.dir = .
source.include_exts = py,png,jpg,jpeg,wav,ogg,ttf
version = 0.1.0
requirements = python3,pygame-ce
orientation = portrait
fullscreen = 1
android.archs = arm64-v8a
p4a.bootstrap = sdl2
p4a.local_recipes = ./p4a-recipes

[buildozer]
log_level = 2
warn_on_root = 1
