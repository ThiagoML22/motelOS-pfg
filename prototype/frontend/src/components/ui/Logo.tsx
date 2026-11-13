import React from 'react';

// El logo de MotelOS en dos capas (public/logo-tinta.png y public/logo-acento.png, sacadas de logo.png): lo oscuro toma
// el color del texto y «OS» con el trazo del medio de la M toman el color de marca del motel. Así cambia cuando la
// gerencia elige otro color en Configuración, y se lee igual en claro y en oscuro.
const Logo: React.FC<{ className?: string }> = ({ className = '' }) => (
  <span role="img" aria-label="MotelOS" className={`logo-marca shrink-0 ${className}`}>
    <span className="logo-tinta" aria-hidden="true" />
    <span className="logo-acento" aria-hidden="true" />
  </span>
);

export default Logo;
