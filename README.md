# Nice Weather

An interactive world map overlay showing where on Earth has the highest probability of "perfect" weather on any given day of the year.

## Features

- **Interactive World Map**: A large, clean map overlay displaying country boundaries and key city names to help users get their bearings.
- **Day of Year Slider**: A slider at the bottom of the map that allows users to slide between all days of the year (1-365) to see how the "perfect" weather zones shift globally over time.
- **Color-Blind Friendly Shading**:
  - The overlay uses a single color hue that contrasts with both blue and green (making it easily readable for red-green color-blind users, such as magenta or orange).
  - Shading is applied only to populated areas (population ≥ 100) with at least a **50% chance** of perfect weather.
  - Opacity scales with the probability: 50% probability is barely visible (high transparency), while 100% probability is nearly opaque.
- **Offline Capable**: All required climate data is downloaded, reformatted, and compressed to run entirely client-side.

## What is a "Perfect Day"?

A day is considered perfect if it meets all of the following criteria:
1. **Maximum Temperature**: $\ge 75^\circ\text{F}$ (preferring dry heat).
2. **Precipitation**: No measurable precipitation.
3. **Sky Conditions**: Mostly sunny.
4. **Humidity**: Not uncomfortably humid.

## Getting Started

*(Instructions will be added as implementation begins.)*
