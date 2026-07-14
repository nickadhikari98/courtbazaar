import React, { useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { MapPin, Navigation, LocateFixed, ExternalLink, ArrowRight } from "lucide-react";
import LiveCourtMap from "./LiveCourtMap";

const delhiCourts = [
  { name: "Dwarka Court", lat: 28.5921, lng: 77.0460, address: "Sector 10, Dwarka, New Delhi, Delhi 110075" },
  { name: "Saket Court", lat: 28.5245, lng: 77.2066, address: "Sector 6, Pushp Vihar, New Delhi, Delhi 110017" },
  { name: "Karkardooma Court", lat: 28.6528, lng: 77.3152, address: "Karkardooma, New Delhi, Delhi 110092" },
  { name: "Tis Hazari Court", lat: 28.6690, lng: 77.2160, address: "Tis Hazari, New Delhi, Delhi 110054" },
  { name: "Patiala House Court", lat: 28.6117, lng: 77.2295, address: "India Gate, New Delhi, Delhi 110001" },
  { name: "Delhi High Court", lat: 28.6273, lng: 77.2385, address: "Sher Shah Rd, India Gate, New Delhi, Delhi 110003" },
  { name: "Rohini Court", lat: 28.7255, lng: 77.1325, address: "Sector 14, Rohini, New Delhi, Delhi 110085" },
  { name: "Supreme Court of India", lat: 28.6227, lng: 77.2394, address: "Tilak Marg, New Delhi, Delhi 110001" },
  { name: "Rouse Avenue Court", lat: 28.6357, lng: 77.2245, address: "Rouse Avenue, New Delhi, Delhi 110002" },
];

function haversineKm(lat1, lon1, lat2, lon2) {
  const toRad = (d) => (d * Math.PI) / 180;
  const R = 6371;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a =
    Math.sin(dLat / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLon / 2) ** 2;
  return R * 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function CourtHighlightPanel({ court, userLocation, locationState, onRequestLocation }) {
  if (!court) return null;
  const mapsUrl = `https://www.google.com/maps?q=${court.lat},${court.lng}`;
  const distance = userLocation ? haversineKm(userLocation.lat, userLocation.lng, court.lat, court.lng) : null;

  return (
    <div className="landing-court-highlight">
      <h4 className="font-display font-bold text-base">{court.name}</h4>
      <div className="mt-3 space-y-2">
        {distance !== null ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Navigation className="w-4 h-4 text-accent flex-shrink-0" />
            <span>
              <span className="font-semibold text-foreground">{distance.toFixed(1)} km</span> away
              <span className="text-xs text-muted-foreground/70"> · Distance from Your Current Location</span>
            </span>
          </div>
        ) : (
          <button
            type="button"
            onClick={onRequestLocation}
            className="flex items-center gap-2 text-sm text-accent font-semibold hover:underline"
          >
            <LocateFixed className="w-4 h-4 flex-shrink-0" />
            <span>
              {locationState === "denied" ? "Location access denied — Enable Location to View Distance" : "Enable Location to View Distance"}
            </span>
          </button>
        )}
        {court.address && (
          <div className="flex items-start gap-2 text-sm text-muted-foreground">
            <MapPin className="w-4 h-4 text-accent flex-shrink-0 mt-0.5" />
            <span>{court.address}</span>
          </div>
        )}
      </div>
      <a
        href={mapsUrl}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-1.5 text-xs font-bold text-accent mt-3 hover:underline"
      >
        View on Map <ExternalLink className="w-3 h-3" />
      </a>
    </div>
  );
}

export default function CoverageSection({ courts = delhiCourts }) {
  const [activeCourt, setActiveCourt] = useState(
    courts.find((c) => c.name === "Delhi High Court") || courts[0]
  );
  const [userLocation, setUserLocation] = useState(null);
  const [locationState, setLocationState] = useState("idle"); // idle | granted | denied | unsupported

  const requestLocation = () => {
    if (!navigator.geolocation) {
      setLocationState("unsupported");
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setUserLocation({ lat: pos.coords.latitude, lng: pos.coords.longitude });
        setLocationState("granted");
      },
      () => setLocationState("denied"),
      { enableHighAccuracy: false, timeout: 8000 }
    );
  };

  return (
    <section id="coverage" className="landing-section bg-slate-50">
      <div className="landing-container">
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-12 items-start">
          {/* Left - Court List + Highlight Panels */}
          <div>
            <h2 className="landing-section-title">
              Coverage Across<br />
              All Major Courts in Delhi
            </h2>
            <div className="mt-8 grid grid-cols-2 gap-x-6 gap-y-3">
              {courts.map((court) => (
                <button
                  key={court.name}
                  type="button"
                  onMouseEnter={() => setActiveCourt(court)}
                  onClick={() => setActiveCourt(court)}
                  className={`landing-court-item text-left w-full ${activeCourt?.name === court.name ? "landing-court-item--active" : ""}`}
                >
                  <div className="w-5 h-5 rounded-full bg-accent/10 flex items-center justify-center flex-shrink-0">
                    <MapPin className="w-3 h-3 text-accent" strokeWidth={2.5} />
                  </div>
                  <span className="font-medium text-base">{court.name}</span>
                </button>
              ))}
            </div>

            <div className="mt-6">
              <CourtHighlightPanel
                court={activeCourt}
                userLocation={userLocation}
                locationState={locationState}
                onRequestLocation={requestLocation}
              />
            </div>

            <Link to="/courts" className="inline-block mt-8">
              <Button className="bg-accent hover:bg-accent/90 text-white font-bold shadow-md shadow-accent/30">
                View All Courts <ArrowRight className="w-4 h-4 ml-1.5" />
              </Button>
            </Link>
          </div>

          {/* Right - Live Map */}
          <LiveCourtMap courts={courts} />
        </div>
      </div>
    </section>
  );
}
