declare const _default: {
    darkMode: "class";
    content: string[];
    theme: {
        container: {
            center: true;
            padding: string;
            screens: {
                '2xl': string;
            };
        };
        extend: {
            colors: {
                border: string;
                input: string;
                ring: string;
                background: string;
                foreground: string;
                primary: {
                    DEFAULT: string;
                    foreground: string;
                };
                secondary: {
                    DEFAULT: string;
                    foreground: string;
                };
                destructive: {
                    DEFAULT: string;
                    foreground: string;
                };
                muted: {
                    DEFAULT: string;
                    foreground: string;
                };
                accent: {
                    DEFAULT: string;
                    foreground: string;
                };
                popover: {
                    DEFAULT: string;
                    foreground: string;
                };
                card: {
                    DEFAULT: string;
                    foreground: string;
                };
                sidebar: {
                    DEFAULT: string;
                    foreground: string;
                    accent: string;
                    border: string;
                };
                success: string;
                warning: string;
            };
            borderRadius: {
                lg: string;
                md: string;
                sm: string;
            };
            boxShadow: {
                soft: string;
                glow: string;
            };
            fontFamily: {
                sans: [string, string, string, string, string, string, string];
                mono: [string, string, string, string];
            };
            keyframes: {
                'fade-in': {
                    from: {
                        opacity: string;
                    };
                    to: {
                        opacity: string;
                    };
                };
                'overlay-in': {
                    from: {
                        opacity: string;
                    };
                    to: {
                        opacity: string;
                    };
                };
                'content-in': {
                    from: {
                        opacity: string;
                        transform: string;
                    };
                    to: {
                        opacity: string;
                        transform: string;
                    };
                };
            };
            animation: {
                'fade-in': string;
                'overlay-in': string;
                'content-in': string;
            };
        };
    };
    plugins: {
        handler: () => void;
    }[];
};
export default _default;
