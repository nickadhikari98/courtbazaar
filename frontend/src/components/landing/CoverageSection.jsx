import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { MapPin, Navigation, LocateFixed, ExternalLink, ArrowRight } from "lucide-react";
import LiveCourtMap from "./LiveCourtMap";
import { getMapCourts } from "@/lib/referenceDataApi";

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
  const mapsUrl = `https://www.google.com/maps?q=${court.latitude},${court.longitude}`;
  const distance = userLocation
    ? haversineKm(userLocation.lat, userLocation.lng, court.latitude, court.longitude)
    : null;

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

export default function CoverageSection() {
  const [courts, setCourts] = useState([]);
  const [activeCourt, setActiveCourt] = useState(null);
  const [userLocation, setUserLocation] = useState(null);
  const [locationState, setLocationState] = useState("idle"); // idle | granted | denied | unsupported

  useEffect(() => {
    getMapCourts()
      .then((data) => {
        setCourts(data);
        // No court is singled out by name — the first serviceable court
        // returned is the default highlight, same as every other court.
        setActiveCourt(data[0] || null);
      })
      .catch(() => setCourts([]));
  }, []);

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
                  key={court.court_id || court.name}
                  type="button"
                  onMouseEnter={() => setActiveCourt(court)}
                  onClick={() => setActiveCourt(court)}
                  className={`landing-court-item text-left w-full ${(activeCourt?.court_id || activeCourt?.name) === (court.court_id || court.name) ? "landing-court-item--active" : ""}`}
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
