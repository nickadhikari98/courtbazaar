import React from "react";
import { Marker, Popup, Tooltip } from "react-leaflet";
import { ShieldCheck, Lock } from "lucide-react";
import MapView, { mapPinIcon } from "@/components/shared/MapView";

const DELHI_CENTER = [28.6304, 77.2177];

function CourtPopup({ court }) {
  const typeLabel = court.type?.replace(/_/g, " ");
  // Display only — strips administrative suffixes like "Delhi (NCT)" -> "Delhi";
  // court.state_name itself is untouched (canonical field, unchanged).
  const stateLabel = court.state_name?.replace(/\s*\([^)]*\)/, "").trim();
  const locationLine = court.district ? `${court.district}, ${stateLabel}` : stateLabel;

  return (
    <div className="min-w-[180px]">
      <div className="font-display font-bold text-sm">{court.name}</div>
      {typeLabel && <div className="text-xs text-muted-foreground mt-1 capitalize">{typeLabel}</div>}
      {locationLine && <div className="text-xs text-muted-foreground mt-0.5">{locationLine}</div>}
      <div className="mt-2">
        {court.serviceable !== false ? (
          <span className="inline-flex items-center gap-1 text-2xs font-bold uppercase text-emerald-700">
            <ShieldCheck className="w-3 h-3" /> Services Available
          </span>
        ) : (
          <span className="inline-flex items-center gap-1 text-2xs font-bold uppercase text-amber-700">
            <Lock className="w-3 h-3" /> Coming Soon
          </span>
        )}
      </div>
    </div>
  );
}

/* Renders only courts with real geocoded coordinates (master Courts
   collection — see backend/scripts/import_court_coordinates.py). Courts
   without coordinates yet are gracefully skipped rather than crashing
   Leaflet with an invalid LatLng. */
export default function LiveCourtMap({ courts = [], className = "" }) {
  const plottable = courts.filter((c) => typeof c.latitude === "number" && typeof c.longitude === "number");

  return (
    <MapView center={DELHI_CENTER} zoom={11} aspectClass="aspect-square" className={className}>
      {plottable.map((court) => (
        <Marker key={court.court_id || court.name} position={[court.latitude, court.longitude]} icon={mapPinIcon}>
          <Tooltip direction="top" offset={[0, -22]} opacity={1} className="court-map-tooltip">
            {court.name}
          </Tooltip>
          <Popup>
            <CourtPopup court={court} />
          </Popup>
        </Marker>
      ))}
    </MapView>
  );
}
