// SPDX-License-Identifier: GPL-2.0-or-later
// Compiled twice: once with the bridge headers and once with the client headers.
#include "court_protocol.hpp"
#include <boost/json/src.hpp>
#include <iostream>
#include <iterator>
#include <string>

int main()
{
    const std::string input(std::istreambuf_iterator<char>(std::cin), {});
    try {
        const auto document = boost::json::parse(input);
        alliance::court_protocol::response(document.as_object());
        std::cout << "COURT PROJECTION ACCEPTED\n";
        return 0;
    } catch(...) {
        // Projection contents may carry account information. Never print them.
        std::cout << "COURT PROJECTION REJECTED\n";
        return 1;
    }
}
