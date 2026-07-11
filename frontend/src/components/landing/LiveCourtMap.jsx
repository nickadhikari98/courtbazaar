import React from "react";
import { MapContainer, TileLayer, Marker, Popup, Tooltip } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

const courtIcon = L.divIcon({
  className: "court-map-pin",
  html: '<div class="court-map-pin-inner"></div>',
  iconSize: [24, 24],
  iconAnchor: [12, 24],
  popupAnchor: [0, -22],
});

const DELHI_CENTER = [28.6304, 77.2177];

export default function LiveCourtMap({ courts = [], className = "" }) {
  return (
    <div className={`landing-map-container aspect-square ${className}`}>
      <MapContainer
        center={DELHI_CENTER}
        zoom={11}
        scrollWheelZoom={false}
        className="w-full h-full"
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {courts.map((court) => (
          <Marker key={court.name} position={[court.lat, court.lng]} icon={courtIcon}>
            <Tooltip direction="top" offset={[0, -22]} opacity={1} className="court-map-tooltip">
              {court.name}
            </Tooltip>
            <Popup>
              <span className="font-semibold text-sm">{court.name}</span>
            </Popup>
          </Marker>
        ))}
      </MapContainer>
    </div>
  );
}
