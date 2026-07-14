import React from "react";
import { Marker, Popup, Tooltip } from "react-leaflet";
import MapView, { mapPinIcon } from "@/components/shared/MapView";

const DELHI_CENTER = [28.6304, 77.2177];

export default function LiveCourtMap({ courts = [], className = "" }) {
  return (
    <MapView center={DELHI_CENTER} zoom={11} aspectClass="aspect-square" className={className}>
      {courts.map((court) => (
        <Marker key={court.name} position={[court.lat, court.lng]} icon={mapPinIcon}>
          <Tooltip direction="top" offset={[0, -22]} opacity={1} className="court-map-tooltip">
            {court.name}
          </Tooltip>
          <Popup>
            <span className="font-semibold text-sm">{court.name}</span>
          </Popup>
        </Marker>
      ))}
    </MapView>
  );
}
