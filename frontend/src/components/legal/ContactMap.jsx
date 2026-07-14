import React from "react";
import { MapContainer, TileLayer, Marker, Popup } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { companyInfo } from "@/config/companyInfo";
import ConfigRequiredBadge from "./ConfigRequiredBadge";

const officeIcon = L.divIcon({
  className: "court-map-pin",
  html: '<div class="court-map-pin-inner"></div>',
  iconSize: [24, 24],
  iconAnchor: [12, 24],
  popupAnchor: [0, -22],
});

export default function ContactMap({ className = "" }) {
  const { lat, lng } = companyInfo.officeCoordinates;

  return (
    <div className={`landing-map-container aspect-[4/3] sm:aspect-[16/9] ${className}`}>
      <MapContainer center={[lat, lng]} zoom={14} scrollWheelZoom={false} className="w-full h-full">
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <Marker position={[lat, lng]} icon={officeIcon}>
          <Popup>
            <div className="text-sm">
              <p className="font-display font-bold">CourtBazaar Office</p>
              <p className="text-xs text-muted-foreground mt-1">Okhla, New Delhi</p>
              {companyInfo.officeAddress.needsConfig ? (
                <div className="mt-1.5">
                  <ConfigRequiredBadge label="Address pending" />
                </div>
              ) : (
                <p className="text-xs mt-1">{companyInfo.officeAddress.value}</p>
              )}
              <p className="text-xs text-muted-foreground mt-1.5">{companyInfo.businessHours.value}</p>
            </div>
          </Popup>
        </Marker>
      </MapContainer>
    </div>
  );
}
