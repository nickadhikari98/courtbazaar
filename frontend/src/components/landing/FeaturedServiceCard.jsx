import React from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { ArrowRight, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";

export default function FeaturedServiceCard({
  icon: Icon,
  image,
  name,
  description,
  cta = "Book Now",
  ctaLink = "/register",
  vertical = false,
  className,
  startingPrice,
}) {
  if (vertical) {
    return (
      <Link
        to={ctaLink}
        className={cn("landing-featured-service landing-featured-service--vertical group", className)}
      >
        <div className="landing-featured-service-badge">
          <Sparkles className="w-3 h-3" />
          Flagship Service
        </div>
        <div className="landing-featured-service-icon landing-featured-service-icon--vertical">
          {image ? (
            <img src={image} alt="" className="w-full h-full object-cover rounded-2xl" />
          ) : (
            <Icon className="w-10 h-10 text-accent" strokeWidth={1.6} />
          )}
        </div>
        <h3 className="font-display font-bold text-xl text-white text-center">{name}</h3>
        {startingPrice && (
          <div className="landing-featured-service-price">
            <span className="landing-service-price-dot" />
            {startingPrice}
          </div>
        )}
        <p className="text-white text-[15px] sm:text-base mt-3 px-1 leading-relaxed text-center">{description}</p>
        <Button
          size="lg"
          className="bg-primary hover:bg-primary/90 text-white font-bold h-12 w-full mt-6 group-hover:shadow-lg group-hover:shadow-accent/40 transition-shadow"
        >
          {cta} <ArrowRight className="w-4 h-4 ml-2" />
        </Button>
      </Link>
    );
  }

  return (
    <div className={cn("landing-featured-service", className)}>
      <div className="landing-featured-service-badge">
        <Sparkles className="w-3 h-3" />
        Flagship Service
      </div>
      <div className="flex flex-col sm:flex-row sm:items-center gap-8">
        <div className="landing-featured-service-icon">
          {image ? (
            <img src={image} alt="" className="w-full h-full object-cover rounded-2xl" />
          ) : (
            <Icon className="w-11 h-11 text-accent" strokeWidth={1.6} />
          )}
        </div>
        <div className="flex-1">
          <h3 className="font-display font-bold text-2xl sm:text-3xl text-white">{name}</h3>
          {startingPrice && (
            <div className="landing-featured-service-price">
              <span className="landing-service-price-dot" />
              Starting at {startingPrice}
            </div>
          )}
          <p className="text-white text-base sm:text-lg mt-3 max-w-xl leading-relaxed">{description}</p>
        </div>
        <Link to={ctaLink} className="flex-shrink-0">
          <Button
            size="lg"
            className="bg-accent hover:bg-accent/90 text-white font-bold h-14 px-8 text-base w-full sm:w-auto"
          >
            {cta} <ArrowRight className="w-5 h-5 ml-2" />
          </Button>
        </Link>
      </div>
    </div>
  );
}
