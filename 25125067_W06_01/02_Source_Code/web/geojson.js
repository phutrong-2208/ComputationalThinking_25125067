"use strict";

// Shared pure export function: used by the browser and offline export tests.
function buildGeoJSON(places, meta, fromSaved = false, now = new Date().toISOString()) {
  return {
    type: "FeatureCollection",
    attribution: "© OpenStreetMap contributors",
    license: "https://opendatacommons.org/licenses/odbl/1-0/",
    exported_at: now,
    query: fromSaved ? null : meta,
    features: places.map(p => ({
      type: "Feature", id: p.id,
      geometry: {type: "Point", coordinates: [p.lon, p.lat]},
      properties: {...p, distance_reference: fromSaved
        ? "Original search center at time of saving" : "Current search center"},
    })),
  };
}
