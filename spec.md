I want to build an interactive world map overlay on a large world map so it's easy to view detail, yet all visible at once. On the bottom is an interactive slider that lets you slide between all the days of the year. For each day, it shows what populated (meaning at least 100 people live there) areas of the world have a high probability of having "perfect" weather that day. "Perfect" is defined as reaching 75 degrees at some point in the day and being mostly sunny and not uncomfortably humid. My perfect high temperature is max temp > 75º F because I like heat as long as it's dry heat. I grew up in phoenix. The overlay will be shaded areas, as granular as we can make them, so lets find detailed climate data to populate the map. We should download all the data needed and convert it into the format we need for our map so that it can function offline. The shading should be a single hue (but with different darkness, achieved with an alpha value as explained below) that is easy to see for color blind people against the world map. It needs to contrast with both blue and green for red-green color blind people like myself. Only areas that have over 50% chance of having perfect that weather will show any shading at all. 50% is barely visible (maybe 90% alpha), while 100% is nearly opaque (nearly 10% alpha)--barely showing the underlying map.

The goal of the map is the slide between the days of the year and see the map change to show where on earth might be having perfect weather that time of year.

Perfect day

Maximum temperature ≥75°F

AND

No measurable precipitation

AND

Mostly sunny

AND

Not uncomfortably humid

Please find the highest quality data sources to convert into the data we'll need for our interactive overlay. 

Also find a high quality map to overlay on that is clean yet makes it easy to determine where shading occurs. For example, it could show boundaries with some key country and city names to help people get their bearings.

I think this map would be useful to a lot of people if we present it cleanly as I've described, and the data is rich enough to be interesting.

We can save stored data and make the map less cluttered if we only shade areas on the map with at least a 50% chance of "perfect" weather for a given day.

Once you have this planned out, fetch, reformat, and reduce all the data to fit our specific case, fetch the map, and create a finished product (could be interactive html with javascript, for example).
