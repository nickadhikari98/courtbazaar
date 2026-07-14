import React, { useEffect, useRef } from "react";
import { MapContainer, TileLayer, useMap } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

export const mapPinIcon = L.divIcon({
  className: "court-map-pin",
  html: '<div class="court-map-pin-inner"></div>',
  iconSize: [24, 24],
  iconAnchor: [12, 24],
  popupAnchor: [0, -22],
});

/* Leaflet only re-measures itself on the window's native "resize" event, so
   a container that changes size for any other reason (grid/flex reflow,
   sidebar toggle, tab becoming visible) leaves the map's internal canvas
   out of sync with its actual box until something calls invalidateSize().
   Watching the wrapper itself covers every case, not just viewport resize. */
function ResizeWatcher({ containerRef }) {
  const map = useMap();

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return undefined;
    const observer = new ResizeObserver(() => map.invalidateSize());
    observer.observe(el);
    return () => observer.disconnect();
  }, [map, containerRef]);

  return null;
}

/* Shared responsive Leaflet wrapper for every map on the site. Owns the
   container sizing/isolation (via .landing-map-container), the OSM tile
   layer, and resize handling — pages only supply center/zoom/aspect ratio
   and their own <Marker>/<Popup> content as children. */
export default function MapView({ center, zoom, aspectClass = "aspect-square", className = "", children }) {
  const containerRef = useRef(null);

  return (
    <div ref={containerRef} className={`landing-map-container ${aspectClass} ${className}`}>
      <MapContainer center={center} zoom={zoom} scrollWheelZoom={false} className="w-full h-full">
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <ResizeWatcher containerRef={containerRef} />
        {children}
      </MapContainer>
    </div>
  );
}
