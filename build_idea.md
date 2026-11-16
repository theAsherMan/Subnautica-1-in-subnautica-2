# Concept for how to build
## Map - Terrain, ambiance, biome

Subnautica 1 already has all the data for it's own terrain, but it is stored as volumetric grids, and Subnautica 2 requires static 3D meshes.  We will need to write a program to convert.

Non-terrain features, such as rocks, resource nodes etc need to be investigated, to determine how to extract them from the first game and place them in the second.  some of these things may even need complete reimplementation.  This process should be broken into two parts.  The process should be implemented as a two stage pipeline.  

The graphics should be upgraded.  low-priority.  I should investigate the quality of image generators for increasing the quality of textures.
Alternatively, downgrading the textures so the difference isn't noticed

Everything else can just be ripped straight from the first game

## Game start and end

We need to skip subnautica 2s tutorial area
as a low priority, we need to add subnautica 1s intro

## ##

ideally, we reuse assets from the second game.  moon fish over peepers for example.  this will also require the changing of some recipes